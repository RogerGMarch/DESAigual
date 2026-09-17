"""LLM-assisted address hypothesis and geocoder candidate review."""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Literal

import duckdb
import httpx
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from tqdm import tqdm

from desfibrilator.geocode import (
    GeocodeResult,
    _feature_distance_km,
    _is_mapbox_region_province_feature,
    _parse_mapbox_result,
    _store_result,
    write_geocode_audit,
)
from desfibrilator.ingest import read_records
from desfibrilator.normalize import (
    address_key,
    municipality_key,
    normalize_aed,
    value_for,
)
from desfibrilator.schema import create_schema


class LLMSettings(BaseSettings):
    """Credentials and endpoints loaded from the local `.env` file."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    gepeto_api_key: str = ""
    gepeto_base_url: str = "https://gepeto.bsc.es/api"
    gepeto_model: str = ""
    mapbox_access_token: str = ""


class AddressHypothesis(BaseModel):
    """A normalized address query proposed by the language model."""

    query: str = Field(min_length=3, max_length=256)
    rationale: str = Field(min_length=1, max_length=500)


class AddressProposal(BaseModel):
    """LLM proposals for one unresolved address."""

    address_key: str
    hypotheses: list[AddressHypothesis] = Field(min_length=1, max_length=3)


class ProposalBatch(BaseModel):
    """Structured output for a batch of address proposals."""

    records: list[AddressProposal]


class CandidateReview(BaseModel):
    """LLM selection from provider-returned candidates."""

    address_key: str
    decision: Literal["accept", "reject"]
    candidate_ref: str | None = None
    precision: Literal["exact", "street", "reject"]
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=1, max_length=800)


class ReviewBatch(BaseModel):
    """Structured output for a batch of candidate reviews."""

    records: list[CandidateReview]


def list_gepeto_models(settings: LLMSettings) -> list[dict]:
    """Return models exposed by the authenticated Open WebUI instance."""
    if not settings.gepeto_api_key:
        raise ValueError("GEPETO_API_KEY is required")
    response = httpx.get(
        f"{settings.gepeto_base_url.rstrip('/')}/models",
        headers={"Authorization": f"Bearer {settings.gepeto_api_key}"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    return payload.get("data", []) if isinstance(payload, dict) else []


def run_llm_geocoding(
    connection: duckdb.DuckDBPyConnection,
    raw_path: Path,
    settings: LLMSettings,
    batch_size: int = 10,
    mapbox_batch_size: int = 100,
) -> int:
    """Run LLM hypothesis generation, Mapbox search, and candidate review."""
    if not settings.gepeto_api_key or not settings.gepeto_model:
        raise ValueError("GEPETO_API_KEY and GEPETO_MODEL are required")
    if not settings.mapbox_access_token:
        raise ValueError("MAPBOX_ACCESS_TOKEN is required")

    records = _unresolved_records(connection, raw_path)
    centers = _municipality_centers(connection)
    bounds = _municipality_bounds(connection)
    existing_reviews = {
        row[0]
        for row in connection.sql(
            "SELECT address_key FROM llm_geocode_reviews"
        ).fetchall()
    }
    proposal_agent, review_agent = _agents(settings)
    total = 0
    for start in tqdm(
        range(0, len(records), batch_size), desc="LLM batches", unit="batch"
    ):
        batch = [
            record
            for record in records[start : start + batch_size]
            if record["address_key"] not in existing_reviews
        ]
        if not batch:
            continue
        proposals = _propose(proposal_agent, batch)
        proposal_map = {item.address_key: item for item in proposals.records}
        query_rows = []
        query_refs = []
        for record in batch:
            proposal = proposal_map.get(record["address_key"])
            if not proposal:
                continue
            for hypothesis_index, hypothesis in enumerate(proposal.hypotheses):
                query_rows.append(
                    (hypothesis.query, record["municipality"], record["province"])
                )
                query_refs.append((record, hypothesis_index, hypothesis))
        candidates = _mapbox_candidates(
            settings.mapbox_access_token,
            bounds,
            centers,
            query_rows,
            mapbox_batch_size,
        )
        candidate_payload = _candidate_payload(query_refs, candidates)
        reviews = _review(review_agent, batch, candidate_payload)
        for review in reviews.records:
            record = next(
                (item for item in batch if item["address_key"] == review.address_key),
                None,
            )
            options = candidate_payload.get(review.address_key, [])
            selected = next(
                (
                    option["feature"]
                    for option in options
                    if option["candidate_ref"] == review.candidate_ref
                ),
                None,
            )
            result = (
                _validated_result(
                    record,
                    review,
                    selected,
                    centers,
                )
                if record
                else None
            )
            _store_review(
                connection,
                review,
                proposal_map.get(review.address_key),
                options,
                settings.gepeto_model,
            )
            if result and result.match_status.startswith("accepted_"):
                _store_result(
                    connection,
                    review.address_key,
                    record["address"],
                    record["municipality"],
                    record["province"],
                    "llm_mapbox",
                    result,
                )
                total += 1
        connection.commit()
    return total


def _agents(settings: LLMSettings):
    """Build hypothesis and review agents for the GEPETO OpenAI API."""
    from pydantic_ai import Agent
    from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
    from pydantic_ai.providers.openai import OpenAIProvider

    model = OpenAIChatModel(
        settings.gepeto_model,
        provider=OpenAIProvider(
            base_url=settings.gepeto_base_url,
            api_key=settings.gepeto_api_key,
        ),
    )
    model_settings = OpenAIChatModelSettings(
        temperature=0.0,
        max_tokens=1200,
    )
    proposal_agent = Agent(
        model,
        output_type=str,
        retries=0,
        model_settings=model_settings,
        system_prompt=(
            "You normalize Spanish AED addresses in Castilla y Leon. "
            "Return only search hypotheses, never coordinates. Preserve uncertainty."
        ),
    )
    review_agent = Agent(
        model,
        output_type=str,
        retries=0,
        model_settings=model_settings,
        system_prompt=(
            "Review geocoder candidates for Spanish AED addresses. "
            "Choose only a supplied candidate_ref or reject. Never invent coordinates."
        ),
    )
    return proposal_agent, review_agent


def _propose(agent, records: list[dict]) -> ProposalBatch:
    prompt = {
        "task": "Create up to three Mapbox search hypotheses per unresolved AED.",
        "rules": [
            "Correct obvious OCR or source typos conservatively.",
            "Keep the original street and number in the first hypothesis.",
            "Do not invent a different street, square, facility, or locality.",
            "Expand hamlet or historic locality names to their parent locality "
            "when supported.",
            "For roads, preserve the road number and kilometre point.",
            "Use facility description and organization only as search context.",
            "Do not output latitude or longitude.",
        ],
        "records": records,
    }
    return _run_json_agent(agent, prompt, ProposalBatch)


def _review(
    agent, records: list[dict], candidates: dict[str, list[dict]]
) -> ReviewBatch:
    prompt = {
        "task": "Select the most plausible geocoder candidate for each AED.",
        "rules": [
            "Only candidate_ref values supplied in the options may be selected.",
            "Reject candidates in another province, municipality, or region.",
            "Use exact only when the address number is supported; otherwise use "
            "street.",
            "Reject if no candidate is defensible.",
        ],
        "records": [
            {
                "address_key": record["address_key"],
                "source": record,
                "options": [
                    option["summary"]
                    for option in candidates.get(record["address_key"], [])
                ],
            }
            for record in records
        ],
    }
    return _run_json_agent(agent, prompt, ReviewBatch)


def _run_json_agent(agent, prompt: dict, output_type):
    """Run a text-mode agent and retry once when its wrapper is not JSON."""
    for attempt in range(2):
        if attempt:
            prompt["correction"] = (
                "Your previous response was invalid. Return only one JSON object "
                "starting with { and ending with }, with no prose or code fence."
            )
        text = agent.run_sync(json.dumps(prompt, ensure_ascii=False)).output
        try:
            return output_type.model_validate(_decode_llm_json(text))
        except (ValueError, json.JSONDecodeError):
            if attempt == 1:
                raise
    raise RuntimeError("Unreachable JSON-agent state")


def _decode_llm_json(text: str) -> dict:
    """Decode plain, fenced, or GEPETO `final_result[ARGS]` JSON output."""
    text = text.strip()
    start = text.find("{")
    if start < 0:
        raise ValueError("LLM response did not contain a JSON object")
    payload, _ = json.JSONDecoder().raw_decode(text[start:])
    return payload


def _mapbox_candidates(token, bounds, centers, rows, batch_size):
    results = []
    with httpx.Client(timeout=60) as client:
        for start in range(0, len(rows), batch_size):
            batch = rows[start : start + batch_size]
            body = []
            for query, municipality, _province in batch:
                item = {
                    "q": query,
                    "types": ["address", "street"],
                    "country": "ES",
                    "bbox": list(bounds),
                    "limit": 5,
                    "autocomplete": False,
                    "language": "es",
                }
                center = centers.get(municipality_key(municipality))
                if center:
                    item["proximity"] = [center[1], center[0]]
                body.append(item)
            response = client.post(
                "https://api.mapbox.com/search/geocode/v6/batch",
                params={"access_token": token, "permanent": True},
                json=body,
            )
            response.raise_for_status()
            payload = response.json()
            results.extend(payload.get("batch", []))
    return results


def _candidate_payload(query_refs, responses):
    output = {}
    for index, (record, hypothesis_index, hypothesis) in enumerate(query_refs):
        response = responses[index] if index < len(responses) else {}
        options = output.setdefault(record["address_key"], [])
        for feature_index, feature in enumerate(response.get("features", [])):
            properties = feature.get("properties", {})
            options.append(
                {
                    "candidate_ref": f"h{hypothesis_index}c{feature_index}",
                    "hypothesis": hypothesis.query,
                    "feature_id": feature.get("id"),
                    "feature": feature,
                    "summary": {
                        "candidate_ref": f"h{hypothesis_index}c{feature_index}",
                        "feature_type": properties.get("feature_type"),
                        "full_address": properties.get("full_address"),
                        "coordinates": feature.get("geometry", {}).get("coordinates"),
                        "match_code": properties.get("match_code"),
                        "context": _context_summary(properties.get("context", {})),
                    },
                }
            )
    return output


def _context_summary(context: dict) -> dict[str, str]:
    """Keep only human-readable Mapbox context fields for the LLM."""
    summary = {}
    for key in ("country", "region", "district", "place", "locality"):
        value = context.get(key, {})
        if value.get("name"):
            summary[key] = value["name"]
        alternate = value.get("alternate", {})
        if alternate.get("name"):
            summary[f"{key}_alternate"] = alternate["name"]
    return summary


def _validated_result(record, review, feature, centers):
    if review.decision != "accept" or not feature:
        return None
    municipality = record["municipality"]
    province = record["province"]
    center = centers.get(municipality_key(municipality))
    if not _is_mapbox_region_province_feature(feature, province):
        return None
    if center and _feature_distance_km(feature, center) > 35:
        return None
    parsed = _parse_mapbox_result(
        {"features": [feature]},
        municipality,
        province,
        center,
        35,
    )
    if not parsed.match_status.startswith("accepted_"):
        return None
    precision = (
        "exact"
        if review.precision == "exact" and parsed.match_precision == "exact"
        else "street"
    )
    return GeocodeResult(
        parsed.latitude,
        parsed.longitude,
        review.confidence,
        parsed.matched_address,
        feature,
        match_precision=precision,
        match_status=f"accepted_llm_{precision}",
    )


def _store_review(connection, review, proposal, options, model):
    input_hash = hashlib.sha256(
        json.dumps(
            {
                "address_key": review.address_key,
                "hypotheses": proposal.model_dump() if proposal else {},
                "options": [option["summary"] for option in options],
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    connection.execute(
        """
        INSERT INTO llm_geocode_reviews
            (address_key, model, prompt_version, input_hash, hypotheses_json,
             candidates_json, selected_candidate_id, review_status,
             review_confidence, review_reason)
        VALUES (?, ?, ?, ?, ?::JSON, ?::JSON, ?, ?, ?, ?)
        ON CONFLICT(address_key) DO UPDATE SET
            model=excluded.model,
            input_hash=excluded.input_hash,
            hypotheses_json=excluded.hypotheses_json,
            candidates_json=excluded.candidates_json,
            selected_candidate_id=excluded.selected_candidate_id,
            review_status=excluded.review_status,
            review_confidence=excluded.review_confidence,
            review_reason=excluded.review_reason
        """,
        [
            review.address_key,
            model,
            "address-review-v1",
            input_hash,
            json.dumps(proposal.model_dump() if proposal else {}, ensure_ascii=False),
            json.dumps([option["summary"] for option in options], ensure_ascii=False),
            review.candidate_ref,
            review.decision,
            review.confidence,
            review.rationale,
        ],
    )


def _unresolved_records(connection, raw_path: Path) -> list[dict]:
    accepted = {
        row[0]
        for row in connection.sql(
            "SELECT address_key FROM aed_geocodes WHERE match_status LIKE 'accepted%'"
        ).fetchall()
    }
    records = []
    seen_keys = set()
    for raw in read_records(raw_path):
        normalized = normalize_aed(raw)
        key = address_key(normalized[1], normalized[2], normalized[3])
        if key in accepted or key in seen_keys:
            continue
        seen_keys.add(key)
        records.append(
            {
                "address_key": key,
                "aed_id": normalized[0],
                "address": normalized[1],
                "municipality": normalized[2],
                "province": normalized[3],
                "facility": value_for(raw, ("ubicacion",)),
                "organisation": value_for(raw, ("empresa",)),
            }
        )
    return records


def _municipality_bounds(connection):
    return connection.sql(
        """
        SELECT min(longitude), min(latitude), max(longitude), max(latitude)
        FROM municipalities
        """
    ).fetchone()


def _municipality_centers(connection):
    return {
        municipality_key(name): (latitude, longitude)
        for name, latitude, longitude in connection.sql(
            "SELECT municipio, latitude, longitude FROM municipalities"
        ).fetchall()
        if name and latitude is not None and longitude is not None
    }


def main():
    """Run model discovery or the LLM-assisted geocoder."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", action="store_true")
    parser.add_argument("--batch-size", type=int, default=3)
    args = parser.parse_args()
    settings = LLMSettings()
    if args.models:
        print(json.dumps(list_gepeto_models(settings), indent=2))
        return
    with duckdb.connect("data/processed/urban_network.duckdb") as connection:
        create_schema(connection)
        applied = run_llm_geocoding(
            connection,
            Path("data/raw/aed.csv"),
            settings,
            batch_size=args.batch_size,
        )
        write_geocode_audit(connection, Path("reports/aed_geocode_audit.csv"))
    print(f"Applied {applied} LLM-reviewed geocodes")


if __name__ == "__main__":
    main()
