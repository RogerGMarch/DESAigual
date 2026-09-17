# Install the project and development tools.
install:
    uv sync --all-extras

# Run the automated test suite.
test:
    uv run pytest

# Check lint and formatting.
lint:
    uv run ruff check .
    uv run ruff format --check .

# Apply Ruff formatting and safe lint fixes.
format:
    uv run ruff check --fix .
    uv run ruff format .

# Create the empty DuckDB schema without requiring source files.
init-db:
    uv run python -m desfibrilator.pipeline --init-only

# Run ingestion and geocoding using config/sources.yaml.
run *args:
    uv run python -m desfibrilator.pipeline {{args}}

# Run Mapbox only for unresolved addresses using MAPBOX_ACCESS_TOKEN.
mapbox *args:
    uv run python -m desfibrilator.pipeline --use-mapbox --skip-cartociudad --skip-fallback {{args}}

# List models exposed by the authenticated GEPETO WebUI.
gepeto-models:
    uv run python -m desfibrilator.llm_geocode --models

# Run LLM-assisted geocode review for unresolved addresses.
llm-geocode:
    uv run python -m desfibrilator.llm_geocode

# Apply high-confidence manual geocode overrides without API requests.
manual-geocode:
    uv run python -m desfibrilator.pipeline --skip-geocoding --apply-manual-review

# Import the completed reviewed AED geocode file without API requests.
import-filled-review:
    uv run python -m desfibrilator.pipeline --skip-geocoding --import-filled-review

# Create a static PNG map with an IGN basemap.
map:
    uv run python -m desfibrilator.map

# Load the derived emergency-hospital locations.
hospitals:
    uv run python -m desfibrilator.hospital --input data/interim/hospitals_geocoded.csv

# Parse the Geofabrik extract into a directed driving network.
network:
    uv run python -m desfibrilator.network --pbf data/raw/castilla-y-leon-latest.osm.pbf

# Parse the Geofabrik extract into a bidirectional walking network.
walking-network:
    uv run python -m desfibrilator.network --mode walking --pbf data/raw/castilla-y-leon-latest.osm.pbf

# Label walking-network components and identify micro-components.
walking-components:
    uv run python -m desfibrilator.network --components --components-only --mode walking

# Calculate current AED-to-hospital travel times.
accessibility:
    uv run python -m desfibrilator.accessibility

# Render the continuous travel-time gradient.
isochrone:
    uv run python -m desfibrilator.isochrone

# Download all Castilla y Leon cadastral building footprints.
catastro-buildings:
    uv run python scripts/download_catastro_buildings.py --extract-footprints

# Use the official building WFS when municipality ZIP downloads are unavailable.
catastro-buildings-wfs:
    uv run python scripts/download_catastro_buildings.py --wfs-fallback --extract-footprints

# Repair cadastral archives containing invalid WFS error documents.
catastro-buildings-repair:
    uv run python scripts/download_catastro_buildings.py --repair-invalid --extract-footprints

# Allocate official municipality population to residential cadastral footprints.
building-population:
    uv run python -m desfibrilator.buildings

# Calculate 5/10/15-minute walking AED population coverage and render the map.
population-access:
    uv run python -m desfibrilator.population_access

# Plot municipality population coverage at 5/10/15 walking minutes.
municipality-plot:
    uv run python -m desfibrilator.municipality_plot

# Plot the population-weighted distribution and median AED proximity.
population-distribution:
    uv run python -m desfibrilator.population_distribution

# Fill missing municipality populations with a documented OSM fallback.
osm-fill-missing:
    uv run python -m desfibrilator.osm_fallback

# Plot municipality coverage distributions with median markers.
municipality-dotplot:
    uv run python -m desfibrilator.municipality_dotplot

# Render León cadastral building footprints colored by walking time to AEDs.
leon-map:
    uv run python -m desfibrilator.leon_map

# Create cadastral building maps for the largest municipalities.
major-city-maps:
    uv run python -m desfibrilator.city_maps

# Prepare Zamora OSM building fallback and refresh its access calculations.
zamora-osm-buildings:
    uv run python -m desfibrilator.osm_buildings

# Render the Zamora OSM building fallback map.
zamora-map:
    uv run python -m desfibrilator.leon_map --municipality-id 49275 --city-name Zamora --buildings data/interim/osm_zamora_buildings.gpkg --output reports/figures/cities/zamora_building_aed_access.png --export data/processed/city_buildings/zamora_building_aed_access.gpkg --building-source "OpenStreetMap buildings"

# Extract the Castilla y León boundary used to mask regional maps.
region-boundary:
    uv run python -m desfibrilator.boundary
