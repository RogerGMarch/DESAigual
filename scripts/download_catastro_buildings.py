"""Download Spanish Cadastre INSPIRE building footprints by municipality."""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import re
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.client import RemoteDisconnected
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from pyproj import Transformer
from tqdm import tqdm

from desfibrilator.config import ProjectConfig

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
GEORSS_NS = {"georss": "http://www.georss.org/georss"}
GML_NS = "http://www.opengis.net/gml/3.2"
USER_AGENT = "desfibrilator-cadastral-buildings/0.1"
MUNICIPALITY_PATTERN = re.compile(r"^\s*(\d{5})-(.+?)\s+buildings\s*$", re.I)
MANIFEST_FIELDS = (
    "municipality_id",
    "municipality_name",
    "province_code",
    "province_feed",
    "feed_updated",
    "archive_url",
    "archive_updated",
    "archive_path",
    "archive_bytes",
    "archive_sha256",
    "source_method",
    "status",
    "error",
)


def main() -> None:
    """Download current municipality archives and optionally extract footprints."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/sources.yaml"))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="download only the first N municipality archives, for testing",
    )
    parser.add_argument(
        "--extract-footprints",
        action="store_true",
        help="extract only *.building.gml files, excluding building parts",
    )
    parser.add_argument(
        "--refresh-feeds",
        action="store_true",
        help="fetch new provincial feeds instead of using cached feed snapshots",
    )
    parser.add_argument(
        "--rehash-existing",
        action="store_true",
        help="recompute checksums for archives already downloaded",
    )
    parser.add_argument(
        "--wfs-fallback",
        action="store_true",
        help="use the official WFS for missing archives instead of ZIP downloads",
    )
    parser.add_argument(
        "--repair-invalid",
        action="store_true",
        help="repair existing archives that contain WFS error documents",
    )
    args = parser.parse_args()
    if args.workers < 1 or args.retries < 1:
        raise ValueError("workers and retries must be positive")

    config = ProjectConfig.from_yaml(args.config)
    source = config.sources["catastro_buildings"]
    raw_root = Path(source["path"])
    feed_template = source["feed_template"]
    wfs_url = source.get("wfs_url", "https://ovc.catastro.meh.es/INSPIRE/wfsBU.aspx")
    province_codes = [str(code).zfill(2) for code in source["province_codes"]]
    raw_root.mkdir(parents=True, exist_ok=True)

    feeds = []
    for province_code in province_codes:
        feed_url = feed_template.format(province=province_code)
        feed_bytes = _feed_bytes(
            raw_root, province_code, feed_url, args.retries, args.refresh_feeds
        )
        feed_root = ElementTree.fromstring(feed_bytes)
        feed_updated = _text(feed_root.find("atom:updated", ATOM_NS))
        feed_path = raw_root / "feeds" / f"{province_code}-{feed_updated[:10]}.xml"
        feed_path.parent.mkdir(parents=True, exist_ok=True)
        if not feed_path.exists():
            feed_path.write_bytes(feed_bytes)
        feeds.extend(_archive_records(feed_root, province_code, feed_url, feed_updated))

    feeds.sort(key=lambda record: record["municipality_id"])
    for record in feeds:
        record["wfs_url"] = wfs_url
    if args.limit is not None:
        feeds = feeds[: args.limit]
    print(f"Found {len(feeds)} municipality archives")

    records = []
    pending = []
    for record in feeds:
        archive_path = (
            raw_root
            / "zips"
            / str(record["province_code"])
            / f"{record['municipality_id']}.zip"
        )
        if not args.rehash_existing and _valid_building_archive(archive_path):
            records.append(_present_archive(record, archive_path))
        else:
            pending.append(record)
    print(f"Archives to download or recheck: {len(pending)}")
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                _download_archive,
                record,
                raw_root,
                args.retries,
                args.rehash_existing,
                args.wfs_fallback or args.repair_invalid,
            ): record
            for record in pending
        }
        for index, future in enumerate(
            tqdm(
                as_completed(futures),
                total=len(futures),
                desc="Downloading cadastral archives",
                unit="municipality",
            ),
            start=1,
        ):
            result = future.result()
            records.append(result)
            print(
                f"[{index}/{len(futures)}] {result['municipality_id']} "
                f"{result['status']}"
            )

    records.sort(key=lambda record: record["municipality_id"])
    manifest_path = raw_root / "manifest.csv"
    _write_manifest(manifest_path, records)
    failures = [
        record
        for record in records
        if record["status"] not in {"downloaded", "downloaded_wfs"}
    ]
    print(f"Wrote {manifest_path}: {len(records) - len(failures)} archives")
    if failures:
        print(f"Failed archives: {len(failures)}; see {manifest_path}")
        raise SystemExit(1)

    if args.extract_footprints:
        extracted = _extract_footprints(records, raw_root / "footprints")
        print(f"Extracted {extracted} building footprint files")


def _archive_records(
    root: ElementTree.Element,
    province_code: str,
    feed_url: str,
    feed_updated: str,
) -> list[dict[str, str | None]]:
    records = []
    for entry in root.findall("atom:entry", ATOM_NS):
        match = MUNICIPALITY_PATTERN.match(_text(entry.find("atom:title", ATOM_NS)))
        if match is None:
            continue
        enclosure = next(
            (
                link.attrib["href"]
                for link in entry.findall("atom:link", ATOM_NS)
                if link.attrib.get("rel") == "enclosure"
            ),
            None,
        )
        if enclosure is None:
            raise ValueError(f"No archive link for municipality {match.group(1)}")
        records.append(
            {
                "municipality_id": match.group(1),
                "municipality_name": match.group(2).strip(),
                "province_code": province_code,
                "province_feed": feed_url,
                "feed_updated": feed_updated,
                "archive_url": enclosure,
                "archive_updated": _text(entry.find("atom:updated", ATOM_NS)),
                "wfs_bbox": _bbox(entry),
                "wfs_srs": _srs(entry),
            }
        )
    return records


def _feed_bytes(
    raw_root: Path,
    province_code: str,
    feed_url: str,
    retries: int,
    refresh: bool,
) -> bytes:
    """Read a cached feed for resumable runs, or fetch the current feed."""
    cached = sorted((raw_root / "feeds").glob(f"{province_code}-*.xml"))
    if cached and not refresh:
        return cached[-1].read_bytes()
    feed_bytes = _fetch(feed_url, retries)
    feed_root = ElementTree.fromstring(feed_bytes)
    feed_updated = _text(feed_root.find("atom:updated", ATOM_NS))
    feed_path = raw_root / "feeds" / f"{province_code}-{feed_updated[:10]}.xml"
    feed_path.parent.mkdir(parents=True, exist_ok=True)
    if not feed_path.exists():
        feed_path.write_bytes(feed_bytes)
    return feed_bytes


def _download_archive(
    record: dict[str, str | None],
    raw_root: Path,
    retries: int,
    hash_existing: bool,
    wfs_fallback: bool,
) -> dict[str, str | None]:
    archive_path = (
        raw_root
        / "zips"
        / str(record["province_code"])
        / f"{record['municipality_id']}.zip"
    )
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    result = dict(record)
    result["archive_path"] = str(archive_path)
    result["error"] = ""
    try:
        was_present = _valid_building_archive(archive_path)
        if not was_present:
            if wfs_fallback:
                _download_wfs_archive(record, archive_path, retries)
            else:
                _download_to_file(str(record["archive_url"]), archive_path, retries)
        if not zipfile.is_zipfile(archive_path):
            raise ValueError(f"Downloaded file is not a ZIP archive: {archive_path}")
        result["archive_bytes"] = str(archive_path.stat().st_size)
        result["archive_sha256"] = (
            _sha256(archive_path) if hash_existing or not was_present else ""
        )
        result["source_method"] = (
            "wfs"
            if (wfs_fallback and not was_present)
            or (was_present and _is_wfs_archive(archive_path))
            else "zip"
        )
        result["status"] = (
            "downloaded_wfs" if result["source_method"] == "wfs" else "downloaded"
        )
    except (OSError, HTTPError, URLError, ValueError) as error:
        result["archive_bytes"] = ""
        result["archive_sha256"] = ""
        result["status"] = "error"
        result["error"] = str(error)
    return result


def _present_archive(
    record: dict[str, str | None], archive_path: Path
) -> dict[str, str | None]:
    """Create a manifest row for a valid archive without reading its contents."""
    result = dict(record)
    result["archive_path"] = str(archive_path)
    result["archive_bytes"] = str(archive_path.stat().st_size)
    result["archive_sha256"] = ""
    result["source_method"] = "wfs" if _is_wfs_archive(archive_path) else "zip"
    result["status"] = "downloaded"
    result["error"] = ""
    return result


def _download_wfs_archive(
    record: dict[str, str | None], archive_path: Path, retries: int
) -> None:
    """Download Building features for one municipality bounding box via WFS."""
    bbox = record.get("wfs_bbox")
    if not bbox:
        raise ValueError(f"Feed entry has no bounding box: {record['municipality_id']}")
    srs = str(record.get("wfs_srs") or "EPSG:25830")
    west, south, east, north = map(float, str(bbox).split(","))
    transformer = Transformer.from_crs("EPSG:4326", srs, always_xy=True)
    west, south = transformer.transform(west, south)
    east, north = transformer.transform(east, north)
    bounds = f"{west},{south},{east},{north}"
    template_root, all_features = _fetch_wfs_features(
        record, bounds, srs, retries, depth=0
    )
    for member in template_root.findall(f"{{{GML_NS}}}featureMember"):
        template_root.remove(member)
    for member in all_features:
        template_root.append(member)
    payload = ElementTree.tostring(
        template_root, encoding="ISO-8859-1", xml_declaration=True
    )
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = archive_path.with_suffix(archive_path.suffix + ".part")
    name = f"A.ES.SDGC.BU.{record['municipality_id']}.building.gml"
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, payload)
    temporary.replace(archive_path)


def _fetch_wfs_features(
    record: dict[str, str | None],
    bounds: str,
    srs: str,
    retries: int,
    depth: int,
) -> tuple[ElementTree.Element, list[ElementTree.Element]]:
    """Fetch a WFS extent, recursively tiling it when the server rejects it."""
    all_features = []
    template_root = None
    start_index = 0
    page_size = 1000
    while True:
        params = {
            "SERVICE": "WFS",
            "VERSION": "2.0.0",
            "REQUEST": "GetFeature",
            "TYPENAMES": "bu:Building",
            "COUNT": str(page_size),
            "STARTINDEX": str(start_index),
            "SRSNAME": srs,
            "BBOX": bounds,
        }
        url = str(record["wfs_url"]) + "?" + urlencode(params)
        payload = ElementTree.fromstring(_fetch(url, retries))
        if payload.tag.endswith("}ExceptionReport"):
            if depth >= 6:
                raise ValueError(
                    f"WFS rejected tiled extent for {record['municipality_id']}"
                )
            west, south, east, north = map(float, bounds.split(","))
            x_mid = (west + east) / 2
            y_mid = (south + north) / 2
            features = []
            first_root = None
            for tile in (
                (west, south, x_mid, y_mid),
                (x_mid, south, east, y_mid),
                (west, y_mid, x_mid, north),
                (x_mid, y_mid, east, north),
            ):
                root, tile_features = _fetch_wfs_features(
                    record,
                    ",".join(str(value) for value in tile),
                    srs,
                    retries,
                    depth + 1,
                )
                if first_root is None:
                    first_root = root
                features.extend(tile_features)
            if first_root is None:
                raise ValueError(f"No WFS response for {record['municipality_id']}")
            return first_root, features
        if template_root is None:
            template_root = payload
        members = payload.findall(f"{{{GML_NS}}}featureMember")
        for member in members:
            local_id = next(
                (
                    element.text
                    for element in member.iter()
                    if element.tag.endswith("}localId") and element.text
                ),
                "",
            )
            if local_id.startswith(str(record["municipality_id"])):
                all_features.append(copy.deepcopy(member))
        if len(members) < page_size:
            break
        start_index += len(members)
    if template_root is None:
        raise ValueError(f"No WFS response for {record['municipality_id']}")
    return template_root, all_features


def _is_wfs_archive(path: Path) -> bool:
    """Identify local fallback archives by their footprint-only contents."""
    with zipfile.ZipFile(path) as archive:
        names = [PurePosixPath(name).name.lower() for name in archive.namelist()]
    return bool(names) and all(name.endswith(".building.gml") for name in names)


def _download_to_file(url: str, path: Path, retries: int) -> None:
    encoded_url = _encode_url(url)
    temporary = path.with_suffix(path.suffix + ".part")
    for attempt in range(1, retries + 1):
        try:
            request = Request(encoded_url, headers={"User-Agent": USER_AGENT})
            with (
                urlopen(request, timeout=120) as response,
                temporary.open("wb") as file,
            ):
                while chunk := response.read(1024 * 1024):
                    file.write(chunk)
            temporary.replace(path)
            return
        except (TimeoutError, OSError, HTTPError, URLError, RemoteDisconnected):
            temporary.unlink(missing_ok=True)
            if attempt == retries:
                raise
            time.sleep(attempt)


def _fetch(url: str, retries: int) -> bytes:
    encoded_url = _encode_url(url)
    for attempt in range(1, retries + 1):
        try:
            request = Request(encoded_url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=60) as response:
                return response.read()
        except (TimeoutError, HTTPError, URLError, RemoteDisconnected):
            if attempt == retries:
                raise
            time.sleep(attempt)
    raise RuntimeError("unreachable")


def _encode_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            quote(parts.path, safe="/"),
            parts.query,
            parts.fragment,
        )
    )


def _bbox(entry: ElementTree.Element) -> str:
    values = list(
        map(
            float,
            _text(entry.find("georss:polygon", GEORSS_NS)).split(),
        )
    )
    if len(values) < 4:
        raise ValueError("Feed entry has an invalid GeoRSS bounding polygon")
    latitudes = values[0::2]
    longitudes = values[1::2]
    return f"{min(longitudes)},{min(latitudes)},{max(longitudes)},{max(latitudes)}"


def _srs(entry: ElementTree.Element) -> str:
    category = entry.find("atom:category", ATOM_NS)
    term = "" if category is None else category.attrib.get("term", "")
    return "EPSG:25829" if term.endswith("25829") else "EPSG:25830"


def _extract_footprints(records: list[dict[str, str | None]], output_root: Path) -> int:
    count = 0
    for record in records:
        archive_path = Path(str(record["archive_path"]))
        municipality_root = output_root / str(record["municipality_id"])
        with zipfile.ZipFile(archive_path) as archive:
            names = [
                name
                for name in archive.namelist()
                if PurePosixPath(name).name.lower().endswith(".building.gml")
            ]
            for name in names:
                destination = municipality_root / PurePosixPath(name).name
                if destination.exists() and _valid_building_gml(destination):
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(archive.read(name))
                count += 1
    return count


def _valid_building_archive(path: Path) -> bool:
    """Return whether an archive contains at least one valid building GML."""
    if not path.exists() or not zipfile.is_zipfile(path):
        return False
    try:
        with zipfile.ZipFile(path) as archive:
            names = [
                name
                for name in archive.namelist()
                if PurePosixPath(name).name.lower().endswith(".building.gml")
            ]
            return bool(names) and any(
                _valid_building_bytes(archive.read(name)) for name in names
            )
    except (OSError, zipfile.BadZipFile, ElementTree.ParseError):
        return False


def _valid_building_gml(path: Path) -> bool:
    """Return whether a local GML contains a non-error building feature."""
    try:
        return _valid_building_bytes(path.read_bytes())
    except (OSError, ElementTree.ParseError):
        return False


def _valid_building_bytes(payload: bytes) -> bool:
    """Return whether XML contains a Building feature rather than an exception."""
    root = ElementTree.fromstring(payload)
    if root.tag.endswith("}ExceptionReport"):
        return False
    return any(element.tag.endswith("}Building") for element in root.iter())


def _write_manifest(path: Path, records: list[dict[str, str | None]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(
            {field: record.get(field, "") for field in MANIFEST_FIELDS}
            for record in records
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _text(element: ElementTree.Element | None) -> str:
    return "" if element is None or element.text is None else element.text.strip()


if __name__ == "__main__":
    main()
