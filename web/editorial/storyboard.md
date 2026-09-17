# CardioResilient — editorial storyboard

Proposal based on the current exported data, 15 September 2026. This is a
storytelling direction, not a new implementation of the live page.

## Editorial premise

**Un desfibrilador en el mapa. ¿A cuántos minutos de casa?**

Suggested standfirst: «El análisis de los edificios y las calles de Castilla y
León muestra cómo cambia el acceso a un DESA, incluso entre ciudades de una
misma provincia».

The current presentation repeats text + regional map, with headings that name
operations (“Contar a quienes pueden llegar”, “Acercarse a León”). Replace those
with findings. Let the graphics answer one question at a time. Keep the existing
sans-serif, subdued palette and restrained navigation. Retain the AED opening,
but shorten its stage and place the research question ahead of the project brand.

## Proposed sequence: approximately 3–4 minutes

1. **The object / the question.** AED above the blurred real map. On scroll, the
   object fades and the map comes into focus. Do not morph an AED into a data point.
   Copy: «Un desfibrilador puede estar en tu municipio. Eso no dice cuánto se tarda
   en llegar hasta él».
2. **The network.** Reveal 1,933 mapped registry records in one progressive pass.
   Small annotation: 2,008 total records; records are not necessarily unique devices.
   Merge the current “Los puntos” and “Parece que hay muchos” scenes.
3. **The first finding.** Give the graphic the full visual stage. «En la población
   analizada, menos de cuatro de cada diez personas tienen un DESA a cinco minutos
   a pie». A 100% horizontal population bar fills to 39.6%, then 58.6% at ten minutes,
   then 65.0% below fifteen. A brace calls out the remaining 35% without a route found
   under the search limit. Keep its population denominator visible: estimates for
   1,828 municipalities, 1,816,060 official residents used as weighting denominator.
   Do not present 35% as measured journeys longer than fifteen minutes.
4. **The comparison.** «Dos ciudades de la misma provincia. Dos accesos distintos».
   A full-width comparison chart shows León and Ponferrada. Reveal five-minute
   markers first (65.45% / 27.5%), then extend to fifteen (98.93% / 63.79%).
   Preview: city-comparison.png. The connecting line shows a change of threshold,
   not change over calendar time. These are modeled access differences, not a
   causal claim about terrain, density or investment.
5. **Back to the buildings.** Zoom region → León → a readable neighborhood; retain
   orientation with a small locator map and explicit place name. Reveal its footprints,
   then move to Ponferrada at the same map scale. Same colors, legend and zoom for
   both. Pause the map long enough to read the comparison. Select neighborhoods
   reproducibly and show whole-city figures beside them; do not imply a crop is a
   representative sample. A return zoom prevents readers losing geographic context.
6. **Show how a journey is measured.** Choose one audited residential building and
   one AED, with an actual computed walking path. Draw the road route progressively
   and label its modeled time. Optionally show a thin straight-line connector before
   the network route. This needs a new route geometry export; the current files
   contain building times and nearest-device IDs, not verified route polylines.
   Do not draw a decorative route or invent a detour. If no verified route is ready,
   use the existing footprint comparison and omit this scene.
7. **A separate access question.** Clear chapter break: «Un DESA y un hospital
   responden a preguntas distintas». Reset the camera to the region. Clearly change
   unit/mode to driving minutes and destinations to 14 emergency hospitals. Reveal
   the continuous surface and label a few verified road-node values directly.
   Do not add walking DESA time to driving hospital time, or imply a sequential
   emergency-care journey. The raster is a nearest-reachable-node approximation,
   not parcel-level routing. Avoid a population histogram based on raster pixels:
   pixels represent land area, not residents. The current maximum is 120.088 minutes.
8. **The invitation.** «Ahora busca tu municipio». Enable gestures and search only
   here, keeping existing city detail, source labels and missing-data feedback.
   Follow with methodology and the short author section.

## Graphic priorities

Build first: large sequential population bar; two-city comparison; consistent
León/Ponferrada camera sequence. These can use the current audited exports.

Build after additional analysis: verified building-to-AED path with building,
AED and node IDs plus routing parameters. Optional city-wide walking-time
cumulative curve needs population weights and explicit censoring at fifteen.
Never join the three known aggregate thresholds into an apparently exact curve.

Potential second investigation: municipal population vs five-minute coverage.
Compute and inspect the relationship before writing a “rural disadvantage” claim.
Use one symbol per municipality, label outliers, and distinguish unknown coverage
from zero. It should answer a new question, not add dashboard density.

## Motion and presentation

- Scroll reveals evidence. Each passage should remain understandable when static.
- Alternate persistent map sections with two full-width chart breaks.
- Keep major camera transitions around 1–1.5 seconds, with stable reading intervals.
- Use opacity and layer emphasis for local findings; avoid continuous spinning,
  looping counters, forced scrolling or incessant camera motion.
- Explain thresholds in text as well as color. Direct labels beat mandatory tooltips.
- Respect reduced motion; show completed routes/bars immediately.
- Mobile: stack the explanation below a readable map/chart; avoid covering most
  of the evidence with opaque text cards in the final explorer.

## Current review limits

The regional coverage scene was visually inspected in the browser: the 39.6%
finding is subordinate to methodology text and the regional dot map. Existing
copy and current data exports were inspected across all story sections. No full
keyboard or assistive-technology audit was performed. The supplied NYT article
could not be opened through the web reader; this proposal is grounded in the
current prototype and its data, not a claimed fresh inspection of that article.

## Added regional chapter: municipality size and access

Run `python -m desfibrilator.municipality_story` to regenerate the analysis and
`population-distribution.png` from all 2,248 municipal features. Tests check size
boundaries, population weighting and exclusion of unavailable access estimates.

Place this chapter after the device network and before the regional coverage
finding. Copy: «Ocho de cada diez municipios tienen menos de 500 habitantes.
En ellos vive aproximadamente una de cada ocho personas de la comunidad».
Exact current figures: 1,808 municipalities (80.4%), 285,075 residents (11.9%).
The nine municipalities with at least 50,000 residents contain 44.3% of population.

Scroll choreography: all municipalities as equally sized dots → sort into
population-size groups → introduce aligned bars comparing share of municipalities
with share of population. Preserve place identity with stable ordering; do not
imply that land area represents population. Then ask: «¿Cómo cambia el acceso
cuando cambia el tamaño del municipio?».

Population-weighted five-minute access in available results is 5.9%, 9.9%, 15.9%,
20.9%, 43.4%, 63.1% in the six ascending groups. Population represented by usable
access results is respectively 85.3%, 75.2%, 81.7%, 77.6%, 80.7%, 71.5% of each
whole group's population. Show these denominators beside any access comparison.
Valladolid lacks an access result; no claim of complete coverage or causation.

A subsequent scatter plot can place municipal population on a logarithmic x-axis
(each tick a tenfold increase) and five-minute coverage on y, one dot per available
municipality. Missing/review results belong in a separate labeled count, not at
zero. Directly label León and Ponferrada to bridge regional pattern and city detail.
The population chapter gives geographic context; the two-city comparison shows
variation that a single size-group average conceals.
