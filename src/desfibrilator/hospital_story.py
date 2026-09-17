"""Export a georeferenced continuous hospital-time surface for the web story."""

import hashlib
import json
from pathlib import Path

import duckdb
import matplotlib
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from pyproj import Transformer
from scipy.spatial import cKDTree

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def export_hospital_surface(
    connection, output: Path, grid_size=500, boundary_path=None
):
    """Color the nearest reachable road node, matching the regional study.

    This is a visual surface of network estimates, not measured travel times
    across every land parcel. Only the administrative boundary masks the surface.
    """
    nodes = connection.execute("""
        SELECT n.longitude, n.latitude, a.network_time_minutes
        FROM road_nodes n JOIN node_hospital_access a USING (node_id)
        WHERE n.longitude IS NOT NULL AND n.latitude IS NOT NULL
        AND a.access_status = 'reachable'
        AND a.network_time_minutes IS NOT NULL
        ORDER BY n.node_id
    """).fetchnumpy()
    hospitals = connection.execute("""
        SELECT hospital_id, name, longitude, latitude FROM hospitals
        WHERE emergency_capable AND longitude IS NOT NULL AND latitude IS NOT NULL
        ORDER BY hospital_id
    """).fetchall()
    if not len(nodes["longitude"]):
        raise ValueError("Hospital network analysis is empty")
    times = np.ma.filled(nodes["network_time_minutes"], np.nan).astype(float)
    project = Transformer.from_crs(4326, 3857, always_xy=True)
    unproject = Transformer.from_crs(3857, 4326, always_xy=True)
    x, y = project.transform(nodes["longitude"], nodes["latitude"])
    west, south, east, north = connection.execute("""
        SELECT min(longitude), min(latitude), max(longitude), max(latitude)
        FROM municipalities WHERE longitude IS NOT NULL AND latitude IS NOT NULL
    """).fetchone()
    xmin, ymin = project.transform(west, south)
    xmax, ymax = project.transform(east, north)
    boundary = None
    if boundary_path is not None:
        import geopandas as gpd

        boundary = gpd.read_file(boundary_path).to_crs(3857).geometry.union_all()
        xmin, ymin, xmax, ymax = boundary.bounds
    # Pixel centers with north at the top match MapLibre image coordinates.
    xx = xmin + (np.arange(grid_size) + 0.5) * (xmax - xmin) / grid_size
    yy = ymax - (np.arange(grid_size) + 0.5) * (ymax - ymin) / grid_size
    gx, gy = np.meshgrid(xx, yy)
    _, indices = cKDTree(np.column_stack((x, y))).query(
        np.column_stack((gx.ravel(), gy.ravel()))
    )
    values = times[indices].reshape(gx.shape)
    valid = np.isfinite(values)
    if boundary is not None:
        from shapely import intersects_xy

        valid &= intersects_xy(boundary, gx, gy)
    minimum, maximum = float(np.nanmin(times)), float(np.nanmax(times))
    cmap = LinearSegmentedColormap.from_list(
        "cardio", ["#418b80", "#d8ad5c", "#cd825a", "#b34f40"]
    )
    rgba = cmap(np.nan_to_num((values - minimum) / max(maximum - minimum, 1)))
    rgba[:, :, 3] = valid.astype(float)
    output.mkdir(parents=True, exist_ok=True)
    plt.imsave(output / "hospital-times.png", rgba)
    result = {
        "minimum": minimum,
        "maximum": maximum,
        "coordinates": [
            list(unproject.transform(a, b))
            for a, b in [(xmin, ymax), (xmax, ymax), (xmax, ymin), (xmin, ymin)]
        ],
        "gridSize": grid_size,
        "clippedToRegion": boundary is not None,
        "reachableRoadNodes": int(np.isfinite(times).sum()),
        "imageVersion": hashlib.sha256(
            (output / "hospital-times.png").read_bytes()
        ).hexdigest()[:12],
        "method": (
            "Nearest reachable road-node driving estimate, extrapolated within the "
            "regional boundary; not parcel-level routing or ambulance response time."
        ),
        "hospitals": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {"id": key, "name": name},
                }
                for key, name, lon, lat in hospitals
            ],
        },
    }
    (output / "hospital-times.json").write_text(json.dumps(result), encoding="utf-8")
    return result


if __name__ == "__main__":
    with duckdb.connect("data/processed/urban_network.duckdb", read_only=True) as db:
        export_hospital_surface(
            db,
            Path("web/public/data"),
            boundary_path=Path("data/interim/castilla_y_leon_boundary.gpkg"),
        )
