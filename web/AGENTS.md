# Prototype Instructions

## DESAigual direction

- Spanish, original editorial scrollytelling with a persistent map and a
  separate municipality explorer after the narrative.
- Keep the main story scroll-led; put filters in
  the explorer. Use restrained sans-serif typography, white backgrounds and muted map colors.
- This is a prototype. Show data gaps and keep the narrative focused on access analysis.
- Preserve the raw data and original DuckDB; regenerate the web export with
  `python -m desfibrilator.story_export` from the analysis project directory.

Run the local server yourself and open the preview in the browser available to this environment. Do not give the user server-start instructions when you can run it.

Before making substantial visual changes, use the Product Design plugin's `get-context` skill when the visual source is unclear or no longer matches the current goal. When the user gives durable prototype-specific design feedback, preferences, or decisions, record them in `AGENTS.md`.

When implementing from a selected generated mock, treat that image as the source of truth for layout, component anatomy, density, spacing, color, typography, visible content, and hierarchy.

Build app UI in `src/`. Keep `.openai/hosting.json`, `worker/index.js`, `scripts/prepare-sites-build.mjs`, and `tests/sites-worker.test.mjs` intact so the same local prototype can be handed to Sites. Before a Sites handoff, run `npm run build` and `npm run test:sites`; the build must leave `dist/client/index.html`, `dist/server/index.js`, and `dist/.openai/hosting.json`.

- Open the story with an original Three.js 3D defibrillator, then reveal the
  persistent regional map on the first scroll. Keep the restrained editorial palette,
  subtle motion, mobile composition and reduced-motion support.
- Selected opening: the refined AED over a softly blurred real map, which comes
  into focus on the first scroll. No model selector in the narrative.
- León scene uses actual Catastro residential footprint polygons with access
  colors. Keep gestures locked in the narrative; enable them in the final explorer.
- Use continuous time gradients for León and the hospital scene. Scene 6 replaces
  the missing-data narrative with hospital driving access; keep data-gap details
  in methodology/explorer. Clearly distinguish walking and driving estimates.

- Current scope: analysis only. Nine narrative sections (0–8), explorer at section 9. Map states are mapped separately in App.jsx.
  Lock all map gestures during the story, including León; enable them only in
  the final explorer. No installation proposals, rankings or planning scenarios.

- Visual direction: Every Neuron (https://everyneuron.com/). Use locally hosted
  Google Sans Flex, normal-weight headings with -0.03em tracking, gray body text,
  generous whitespace and a transparent masthead without a background or border.
  Remove the “Ahora mira los huecos” scene; retain data limitations in methodology.

- Explorer city footprints are driven by `data/cities.json`, not a León-only
  condition. Fetch and cache each city on selection; preserve source labels
  (Catastro for eight cities, OpenStreetMap for Zamora). Missing city geometry
  keeps the municipal view. Hospital surface is clipped to the regional boundary
  and its continuous scale follows actual finite network times without a fixed cap.

- Hospital visualization must match the current Python study: nearest reachable
  road node extrapolated within the regional boundary, without the old 5 km or
  null-node holes. Version the raster URL by its content hash to refresh caches.
- Buildings at or beyond 15 minutes and those with no route found under the
  search limit are red. Keep the null times as null and explain them in the legend.

- Editorial tone: direct, factual Spanish, with findings as headlines. Avoid
  poetic phrases, rhetorical slogans and decorative titles. The approved rebuild
  alternates full-width data charts with maps: population distribution, five-
  and fifteen-minute access, municipal scatter plot, León/Ponferrada comparison,
  building zooms at the same scale, then the separate hospital-driving analysis.
  Keep denominators beside charts; group detailed limitations in methodology.

- Combine the 5/10/15-minute coverage thresholds in one chart. Connect the
  population distribution to population-weighted coverage, then to municipal
  differences. Label the population axis logarithmic (base ten); coverage stays
  linear so zeros remain visible. Show León and Ponferrada maps before their
  comparison chart. Explain hospital driving access as additional territorial
  context, not an emergency response estimate or an added DESA journey.
- Use “Sin cálculo de acceso disponible” instead of “Sin resultado validado”.
  Explain missing inputs vs excluded data joins; neither means coverage zero.

- Accepted editorial focus: territorial inequality in estimated AED access.
  Ground general claims in `editorial/references-inequality.md`; literature
  supports relevance and method, not validation of local numerical results.
  Do not call walking thresholds clinical protection, infer income/rurality
  from municipal population alone, or translate access differences into deaths.

- Main narrative now centers on population without a route under 15 minutes,
  with a separate gray category for residents of municipalities without an
  available calculation. Shares refer only to the available results. Hospital
  travel time is an expandable complementary map after the explorer. The log
  scatter remains expandable under the population distribution of access.
  Scientific references are linked inline and listed in methodology.

- Copy reference: Roger’s Rampa (https://www.rampa.space/es). Explain the concrete
  human problem, what the analysis does, and what its findings make visible.
  Use active, direct Spanish; avoid repeatedly interrupting findings with caveats.
  Keep essential denominators and missing-data categories beside charts, and
  detailed limitations in Fuentes y método. Do not turn stronger writing into
  unsupported clinical or causal claims.

- Explorer: retain municipal coverage colours at regional zoom after a city is selected. DESA markers use dark ink; 15-minute/out-of-search-range access uses brick red, never missing-data gray. Preserve a separate no-calculation category.

- September 16 network update: walking search now extends to 360 minutes; reporting thresholds are inclusive 5/10/15 minutes. Snap within 500 m to components with at least 10 nodes. Null means no calculated route, not >15 minutes. Preserve registry locations separately from routing eligibility. Menu stays sticky with a translucent backing for readability.

- Explorer mouse-wheel scrolling stays disabled so page scrolling does not zoom the map. Zoom buttons and pinch remain available; minimum zoom fits Castilla y León to the current viewport.
