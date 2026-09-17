# CardioResilient — prototype QA

## Scope and visual evidence

- Approved visual reference: https://everyneuron.com/.
- Implementation: http://127.0.0.1:4186/.
- Source visual truth: the user's map-led editorial brief, plus the inspected
  Every Neuron opening. This is an original CardioResilient design, not a clone.
- Source and implementation screenshots were shown together in the browser-tool
  response titled “Complete the desktop visual comparison”. Screenshots are
  recorded inline in the task; no local screenshot files were saved.
- Desktop comparison viewport: 1440 × 960 CSS px, same browser and capture
  density. Browser screenshots omit the scrollbar area; no artificial scaling
  or cropping was applied. An earlier source capture used a different viewport;
  it was recaptured before comparison.
- Responsive verification: 390 × 844 CSS px. Earlier observations also covered
  the narrower desktop layout at approximately 721 px wide.
- State: opening; additional captures cover the first registered-device reveal,
  León's building view, the explorer and the missing-data state for Valladolid.

## Findings and fixes

1. **P2 — italic face was not loaded.** The font-synthesis setting prevented
   intended italics from appearing. Imported the actual Newsreader italic font.
   Later captures show the intended italic title hierarchy.
2. **P2 — map sizing after responsive changes.** Initial captures retained a
   camera framed for the previous viewport. Added ResizeObserver-driven camera
   updates, a map-load generation counter and explicit padding reset before
   fitting the region. The verified first-scene desktop capture fills the map
   panel, and the León transition frames the selected case correctly.
3. **P2 — phone headline words joined.** Hiding hard line breaks concatenated
   words. Kept the line breaks and adjusted the narrative overlay position.
   The phone capture and DOM text check confirm readable words and no horizontal
   document overflow.
4. **P2 — partial-name search beat exact matches.** “Salamanca” selected
   “Doñinos de Salamanca”. Exact names now rank first, followed by prefixes and
   substring matches. Browser verification selected Salamanca (INE 37274), and
   the regression test covers accent-insensitive matching.
5. **P2 — comparison sizes differed for partial proposals.** The reveal now
   compares exactly as many ranked candidates as the reader selected. Both
   three-location and one-location proposals were checked in the browser.

## Required design surfaces

- **Typography:** locally served Newsreader regular/italic display text and DM
  Sans UI text. Intentional editorial adaptation from the reference's sans-serif
  presentation. Headlines, percentages and source notes remain distinct.
- **Spacing:** persistent map occupies 62% of the desktop width; narrative uses
  a narrow left column. Phone text overlays the persistent map. Source reference
  and prototype both give the visualization visual priority and avoid dashboard
  cards; different exact proportions are intentional.
- **Colors:** original warm paper, dark green-gray text, muted red DESA markers
  and teal/amber/red access encoding. Unknown results use hollow markers rather
  than being assigned a bad-access color.
- **Image/data quality:** actual local OSM road geometry, official municipality
  points and accepted geocodes. The map is live data rendering, not a raster
  approximation. No external-page artwork was copied into the implementation.
- **Copy:** Spanish narrative, source labels, partial-coverage disclosure,
  explicit modeling assumptions and labelled illustrative candidate rankings.
  No claims of a completed optimization or network disruption experiment.

## Functional verification

- Story anchor navigation and scroll-driven scene/legend changes.
- Regional-to-León camera transition and building access colors.
- Municipality search: León, Valladolid and corrected exact Salamanca match.
- Missing access state preserves the municipality's official population.
- Proposal selection, equal-size reveal and priority selector.
- Desktop and phone layouts; phone document width does not exceed the viewport.
- Main links, downloads and methodology disclosure elements have real targets.
- Browser console: no application errors observed. A transient map-fit warning
  occurred during earlier resize/HMR iteration; padding handling was corrected.
- Reduced motion is implemented in CSS and camera/point animation code; no
  operating-system preference was changed to test it.

The full-view captures were readable enough to review the relevant hierarchy,
labels and controls. Separate focused captures of the municipality search and
missing-data result were also inspected during interaction checks.

## Automated validation

- Python suite: 29 tests passed, including crosswalk mismatch, identical and
  conflicting building IDs, and a read-only export integrity regression.
- Python Ruff lint and format checks passed.
- Frontend search/ranking tests: 3 passed.
- Production build passed; MapLibre produces the expected large-bundle warning.
- Starter hosting-package checks: 4 passed. No deployment was performed.

## Remaining scope / polish

- Missing municipal data, full DuckDB regeneration and real optimization / road
  failure models remain analysis work, and are disclosed in the prototype.
- The map supplies simplified major-road context, not all pedestrian streets.
- No claim is made that accessibility has been medically validated or that a
  comprehensive assistive-technology audit has been performed.

final result: passed

## Three.js introduction — 2026-09-15

Added an original white-and-teal procedural AED hero. Desktop visual inspection
at 1440×960 confirms the device, headline and caption fit. The first-scroll link
reveals the existing MapLibre scene correctly; browser error log is empty.
The component disposes geometries, materials, textures, renderer and listeners
on cleanup. Reduced motion fixes the pose and removes the fade; WebGL initialization
failure has a CSS fallback. Existing three frontend data tests and production
build pass. Three.js adds approximately 133 KB gzip to the frontend bundle;
Vite still reports a large-chunk warning.

Mobile inspection at 390×844 confirms the device above the narrative card.
Returning to the opening restores the 3D scene.

## Anatomical heart alternative — 2026-09-15

Added marxtrax's CC BY 4.0 textured cutaway heart, with attribution in the hero,
source notes and local license file. Adapted its legacy material to current glTF
PBR; retained diffuse, normal and occlusion textures. The pulse is illustrative.
Desktop (1440×960) and mobile (390×844) captures confirm the model fits. Switching
to the AED and back works; mobile first-scroll still reveals the map. Model
loading has status/error states and late loads are disposed after unmount.
Asset payload is 8.8 MB; texture optimization remains a production consideration.

## Refined AED and blurred map — 2026-09-15

Returned to the AED-only introduction. Added casing gasket, handle grip, side
ribs, screws, status indicator and crisp canvas-printed screen, torso and control
symbols. The real map is softly blurred/muted behind the device and returns to
full clarity on the first scroll. Desktop 1440×960 and mobile 390×844 visually
checked; mobile scroll transition verified. Production build passes. One interim
HMR syntax error was fixed before the successful build and visual checks.

## León cadastral footprints — 2026-09-15

Replaced 8,633 building centroids with their actual Catastro Polygon/MultiPolygon
footprints, joined by building ID. Holes are preserved. Added outlined fills and
a closer initial camera. Enabled wheel, double-click, pinch and pan in scene 6,
with +/- buttons. Browser inspection confirms footprint rendering and successful
zoom from a 200 m to a 100 m scale. Python suite: 30 passed; Ruff checks pass.

## Continuous gradients and hospital scene — 2026-09-15

León footprints now interpolate actual walking minutes continuously, with nulls
gray. Replaced scene 7 with a georeferenced driving-time raster from the existing
hospital network analysis (14 emergency destinations; range 0–120.088 minutes).
The 500×500 surface uses the nearest road node; missing routes and >5 km
extrapolation are transparent. This mask is a documented departure from the
original unrestricted nearest-reachable-node figure. White outlined hospital
markers remain; unrelated point layers are hidden. Mobile and desktop hospital
scene visually inspected. Python suite: 31 passed; frontend build and tests pass.

## Analysis-only story — 2026-09-15

Removed four planning scenes, the placement exercise, candidate map layers and
planning methodology. Story now has eight scenes followed by the explorer.
Disabled drag/pinch/wheel/double-click/keyboard/box-zoom during the narrative;
its map canvas also ignores pointer events. Enabled gestures and +/- only in
the final explorer. Browser checks confirm eight sections, pointer-events:none
in the hospital story, pointer-events:auto in the explorer, and working zoom.


## Every Neuron typography refinement · 15 September 2026

Inspected the live reference: Google Sans Flex, heading weight 400, tracking
-0.03em, gray sans-serif body text and generous whitespace. Applied the same
locally hosted font, white background, lighter hierarchy and transparent masthead.
Removed “Ahora mira los huecos”; updated all map, legend and explorer scene indices.

Checked desktop at 1264×720 and mobile at 390×844: headings fit without horizontal
overflow, the masthead computes to transparent, seven narrative sections remain,
the hospital gradient and regional border render, and the map remains locked in
the story and becomes explorable at the final section. Production build passed
with the existing large-chunk warning.

## Expanded city footprints · 15 September 2026

Search now discovers nine city layers from the exported manifest (58,811
residential polygons). Browser checks confirmed Burgos and Zamora polygon
rendering, correct walking legends, Zamora's OSM attribution, and Valladolid's
explicit fallback to municipal coverage. Hospital raster was visually checked
with the regenerated boundary mask. City fetches are cached and cancelled when
selection changes; stale layers clear during loading. City cameras center on
the median building location so municipal centroids do not frame empty outskirts.

Validation: 33 Python tests, three frontend tests, Ruff checks and production
build. The hospital regression includes a 240-minute value to verify there is no
old fixed cap, plus transparent off-boundary pixels and preserved missing routes.

## Isochrone method correction and red threshold · 15 September 2026

Matched the web raster to the updated analysis: nearest reachable road node,
without the old 5 km/null-node mask. Browser verification shows the continuous
surface filling the regional boundary. Raster URLs include a content hash.
Building null results now render red alongside times at/above 15 minutes;
the legend distinguishes these cases and source nulls are preserved.
33 Python tests and production build passed; Ruff passed.

## Factual editorial rebuild · 15 September 2026

Replaced the seven-section narrative with ten sections, followed by the explorer.
Copy now states findings directly. Added full-width population bars, 5/15-minute
coverage graphics, a municipal population/access scatter, and a two-city
comparison. León and Ponferrada use the same map zoom and colors. Kept the AED
opening, hospital surface, nine city datasets, methodology and author biography.

Verified 1264×800 desktop and 390×844 mobile views: population chart, responsive
scatter and Ponferrada footprints render; no horizontal page overflow. Story map
reports locked; final explorer reports explorable. Four frontend data tests pass,
including population-band boundary/denominator checks. Production build and
format checks pass, with the existing large-bundle warning. Reduced motion is
handled in chart CSS and the existing map camera logic.

## Narrative consolidation · 15 September 2026

Merged access sections into one cumulative 5/10/15-minute graphic; reordered
León and Ponferrada maps before their comparison. Narrative now has nine
sections and explorer index 9. Population → weighted access → municipal
variation transitions are explicit. Scatter axis includes base-ten gridlines
and logarithmic labeling; coverage remains linear, preserving zero results.
Replaced vague missing-result labels with missing-calculation explanations and
399 incomplete / 21 data-join-issue counts from the current exported statuses.
Hospital section explains why distance to hospital services complements DESA
access and keeps modes and limitations separate. Desktop chart and hospital
layouts verified; four frontend tests and production build passed.

## Inequality-centered refinement · 15 September 2026

Main story now distinguishes estimated access from unavailable calculations,
quantifies approximately 635,000 residents with no route found under fifteen
minutes, and shows their distribution by municipality population. Group counts
come from current exports; missing/review populations stay in a separate gray
category. Inline citations link to four scientific references in methodology.
Hospital map renders on opening a complementary section after the explorer;
the logarithmic municipal scatter remains available in an expandable detail.
Desktop checks confirmed the new chart and independently mounted hospital map.
Five frontend tests pass, including preservation of unknown population and total
population conservation; production build passes with its existing size warning.
