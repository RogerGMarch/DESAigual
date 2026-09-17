## Current narrative scope

Analysis only: nine scroll-led sections, ending with hospital driving access,
then a municipality explorer. All map gestures are locked during the story,
including León. Pan, wheel/pinch/double-click/keyboard zoom and +/- controls
are available in the final explorer. Choosing León there shows its footprints.
Installation proposals, ranking scenarios and their explanatory UI have been
removed. Earlier implementation notes below describe prototype history.

# CardioResilient

An original Spanish-language scrollytelling prototype about DESA accessibility
in Castilla y León. React + Vite + MapLibre GL JS. All map geometry and fonts are
served locally; there is no map API token or remote tile dependency.

## Run

From the analysis project root, export the data:

```sh
.venv/bin/python -m desfibrilator.story_export
```

Then, from `web/`:

```sh
npm ci
npm run dev -- --host 127.0.0.1 --port 4186
```

The prototype is currently previewed on port 4186. Generated public data and
`node_modules/` are ignored by Git. Regenerate data before running a fresh clone.

## What works

- Twelve scroll-controlled scenes sharing one persistent map.
- Modeled municipality coverage and a building-level view of León.
- Explicit missing-data and legacy-crosswalk review states.
- Municipality search (accent-insensitive, exact name ranked first).
- An optional placement exercise using up to 3, 5, 10 or 20 municipal centres.
- Equal-size comparison after the reader requests a reveal.
- Three descriptive candidate rankings; the same point count transitions
  between destinations when scrolling through the final scenes.
- Reduced-motion support, keyboard-accessible search and a responsive layout.
- Methodology, source attribution and downloadable GeoJSON / summary JSON.

## Data corrections and limits

`story_export.py` opens the DuckDB read-only. It collapses identical building
records before joining and excludes conflicting building keys and suspect
legacy Cadastre-to-INE assignments. Coverage fractions are weighted by official
municipal population. The export currently includes 1,827 usable municipality
results; 421 have no usable result, including 21 potentially suspect code
assignments (some were already missing from the original results).

The upstream population importer has also been fixed: Cadastre IDs are never
used as an INE fallback, identical footprints are removed before allocation,
and conflicting duplicate building identities are rejected. The original
database has **not** been regenerated. A full regeneration can be done through
the existing building-population and population-access commands after resolving
unmatched municipality names.

The population, equity and spatial-redundancy lists are **illustrative rankings**,
not an optimisation solver. The third uses equirectangular straight-line distance
to a second distinct registered location. There is no road-failure experiment,
predicted coverage improvement, or emergency-response model. Comparisons report
overlapping selections only; they do not score effectiveness.

The driving roads displayed are a simplified major-road context layer from the
local OSM extract, not the complete pedestrian graph used in the analysis.

## Project structure

- `src/App.jsx`: story, municipality explorer and comparison UI.
- `src/MapView.jsx`: map layers, camera and point transitions.
- `src/data.js`: loading, search and deterministic candidate rankings.
- `src/styles.css`: typography, palette, responsive layout and reduced motion.
- `public/data/`: generated, ignored public-data exports.

## Validation

```sh
node --test tests/data.test.mjs
npm run build
npm run test:sites
```

Python validation runs from the parent directory:

```sh
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

This project is a local preview. Deployment is a separate step.

### 3D opening

The first scene uses an original procedural Three.js AED model in
`src/DefibrillatorIntro.jsx`: molded shell, bumper, handle grips, screen graphic,
electrode illustration, controls and fasteners. A blurred, muted version of the
actual MapLibre map sits behind it and comes into focus on the next scene.
Reduced-motion preferences disable movement and transitions. A CSS device
fallback appears if WebGL cannot initialize. Rendering skips inactive scenes
and hidden tabs. No remote model or texture assets are required for this opening.

The earlier heart experiment is no longer loaded. Its assets and CC BY 4.0
license remain in `public/models/heart/` for reference.

### León building geometry

`story_export` joins original Catastro footprint polygons to audited access rows
by building ID. It preserves courtyards and multipart footprints, removes exact
geometry duplicates and rejects conflicting IDs. The León story scene supports
pan, wheel/pinch/double-click zoom and +/- controls; scrolling over the text
continues the narrative. Other story scenes keep their automatic camera behavior.

### Continuous travel-time scales

León's building fills interpolate continuously across 0, 5, 10 and 15 walking
minutes; nulls remain gray. Scene 7 presents hospital driving access from the
existing `node_hospital_access` analysis, with 14 emergency hospitals and a
0–120.1-minute scale. `python -m desfibrilator.hospital_story` exports a 500×500
Web Mercator raster and georeferencing metadata. Each pixel uses its nearest
road node; no-route nodes and cells farther than 5 km from a node are transparent.
This limits extrapolation compared with the original figure. The layer is an
approximate surface, not exact isochrone boundaries or ambulance response times.
`story_export` also regenerates this layer when hospital analysis is present.


## Expanded city analysis

The export now discovers `data/processed/city_buildings/*_building_aed_access.gpkg`
and joins their geometry to current audited DuckDB access rows by building ID.
It writes `public/data/cities.json` and one GeoJSON per supported municipality.
Only the selected city's geometry loads in the explorer; León is already loaded
for the story. Available: Ávila, Burgos, León, Palencia, Ponferrada, Salamanca,
Segovia, Soria and Zamora (58,811 residential footprints). Valladolid has no
available city footprint file yet. Zamora is explicitly labeled OpenStreetMap.

Regenerate with `python -m desfibrilator.story_export` from the analysis root.
The hospital raster now uses the cached regional boundary for extent and mask.
The refreshed database contains 2,036,890 road nodes and 1,999,520 finite times;
the observed maximum remains 120.088 minutes despite the wider 360-minute search
bound. Walking estimates retain their separate 15-minute search limit.


### Hospital surface alignment

The web surface now matches `isochrone.py`: nearest reachable road-node time,
extrapolated inside the administrative boundary. The old null-node and 5 km
masks are removed. A raster content hash versions the image URL. This is a
visual approximation, not a route calculated from each parcel. Building values
at/above 15 minutes and missing results below the search limit both render red;
missing times remain null in the data.


## Editorial rebuild

Ten sections now alternate full-width charts and the persistent map. Chart
values are derived from current exports: population-size distribution, 5/15
minute coverage, a logarithmic population/access scatter and a León/Ponferrada
comparison. Narrative section IDs and map states are separated. Both city
scenes use zoom 14.2; gestures unlock only in section 10, the explorer.
Headline copy is factual Spanish. Hospital access is a separate driving measure.
Reduced-motion preferences disable chart reveals and camera animation.


### Narrative consolidation

Nine narrative sections precede explorer section 9. Coverage thresholds share
one chart; the logarithmic population plot links into the León and Ponferrada
maps, followed by their comparison chart. Hospital access adds geographic context
about distance to emergency hospitals, with its driving mode and limitations
explicit. Missing municipal access calculations are explained in plain language.


### Inequality-focused narrative

The primary findings now concern estimated population outside the 15-minute
search threshold, separated from population in municipalities without results.
`accessPopulationGroups` derives covered, outside-threshold and unknown counts
from current municipality exports. The initial export yields approximately
635,220 people outside the threshold, 82.8% in municipalities below 10,000
residents, among available results only. References are linked in context.
The municipal log scatter is expandable; hospital analysis is an independently
mounted complementary map after the explorer.
