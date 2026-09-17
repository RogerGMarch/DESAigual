# CardioResilient — story and data readiness

Inspected 15 September 2026. All counts below come from read-only queries of
`data/processed/urban_network.duckdb`, the population audit, and pipeline source.
The database and raw data were not changed.

## Editorial direction

A Spanish-language, map-led visual story, followed by a separate explorer.
Keep the map visible through most of the narrative. Scroll controls the camera,
layer visibility, and emphasis. Use white space, restrained typography, a muted
basemap, and a small consistent palette for access categories. Avoid a dashboard
layout in the story. Respect reduced-motion settings and provide a readable
mobile narrative.

Opening: **Cuando cada minuto cuenta, el territorio también decide.**

Keep two journeys distinct: modeled walking access from residential buildings
to a DESA, and modeled driving access from a DESA to an emergency hospital.
Neither measures observed emergency response times.

## Verified inventory

| Item | Current database |
| --- | ---: |
| Municipality rows / distinct INE codes | 2,248 / 2,248 |
| Official population in municipality table | 2,398,500 |
| DESA source records / distinct `aed_id` values | 2,008 / 1,927 |
| Accepted DESA records using existing pipeline helper | 1,933 |
| Distinct `aed_id` values among those accepted records | 1,857 |
| Municipalities with walking-access results | 1,845 |
| Municipalities without walking-access results | 403 |
| Building-population rows | 744,461 |
| Distinct `(building_id, municipality_id)` values | 744,400 |
| Emergency hospitals | 14 |

Source files were retrieved on 7–8 September 2026; exact URLs and checksums are
in `config/sources.yaml`. Building access results were calculated on
15 September 2026.

## Resolve before publishing headline statistics

1. **Incomplete territory.** Valladolid, Zamora, Laguna de Duero, Medina del
   Campo and other municipalities have no walking-access output. Show missing
   coverage explicitly; never classify missing results as poor access.
2. **Search capped at 15 minutes.** `population_access.py` searches for a DESA
   only within 15 network minutes and converts results at or beyond that limit
   to null. Null combines outside-search-range and unreachable cases. Use
   “Sin acceso identificado dentro del umbral de 15 min”; do not invent 18- or
   25-minute values. The implementation excludes the exact 15-minute boundary.
3. **Population duplication.** Several municipality totals are approximately
   twice the official population: for example Miranda de Azán has about 902
   modeled people against 451 in the municipality table, and Milagros about 818
   against 409. Trace the allocation/import grain before publishing regional
   percentages. Do not silently normalize away the underlying issue.
4. **Building joins can multiply rows.** Joining the two building tables on
   `(building_id, municipality_id)` yields 744,599 rows, exceeding the 744,461
   rows in each input. Resolve the duplicate keys before exporting a joined map.
5. **DESA record grain.** Source records, distinct IDs, accepted addresses and
   physical devices are different counts. Say “registros” until duplicates and
   device identity have been audited.
6. **Audit mismatch.** `building_population_audit.csv` has 2,246 rows (1,875
   `ok`, 371 `error`), whereas the municipal source has 2,248 rows and the access
   table has 1,845 municipalities. Reconcile these sets by identifier.
7. **Model interpretation.** Population is allocated to residential footprints
   using area weighting. Walking speed is 4.8 km/h. Check snapping distances,
   missing connections, opening hours and geocoding precision before treating
   accessibility as practical device availability.
8. **Missing analysis.** No implemented optimisation, disruption experiment,
   equity objective, resilience objective or age-65-plus input was found in the
   inspected source, configuration and model files.

## Proposed twelve scenes

| Scene | Visual transition | Evidence / dependency |
| --- | --- | --- |
| 01 · El territorio | Quiet regional map and opening sentence | Geographic basemap |
| 02 · La red registrada | Reveal accepted DESA points | Label source records and mapped subset separately |
| 03 · Parece cerca | Gentle zoom; distinguish concentrated and sparse areas | Registered locations; avoid an unsupported coverage claim |
| 04 · La pregunta cambia | Reveal road / walking network | “Estar cerca no significa poder llegar rápido” |
| 05 · Caminar hasta un DESA | Show modeled 5-, 10-, 15-minute access | Repair population grain; retain unknown category |
| 06 · Lo que el mapa aún no sabe | Reveal municipalities without results | Missing coverage is a substantive scene |
| 07 · Una escala humana | Zoom into León; show buildings and DESAs | Available León GeoPackage; verify joins before export |
| 08 · Volver al territorio | Reveal areas without identified access within search bound | Current outputs support threshold coverage, not exact times beyond it |
| 09 · Una red puede fallar | Introduce a clearly defined interruption | Requires a computed disruption scenario |
| 10 · Medir la consecuencia | Update affected population / municipality counts | Requires baseline-versus-disrupted results |
| 11 · Veinte nuevas oportunidades | Candidate locations reduce to selected sites | Requires explicit candidate set, budget and optimisation |
| 12 · Tres decisiones | Transition between population, equity and resilience solutions | Requires comparable outputs under the same budget |

Until the missing models exist, scenes 09–12 belong in the implementation plan,
not in the published story as simulated findings.

## Explorer after the story

- Municipality search across all 2,248 municipalities, with clear unavailable
  states for the 403 without access results.
- Show official population, modeled coverage, source date and model limitations.
- Optional placement challenge: select up to five candidate sites, undo or reset,
  then compare equal budgets using the same objective and network calculation.
- Only expose strategy and budget controls once corresponding calculations
  exist. A five-site user proposal cannot fairly be scored against twenty sites.

## Implementation approach

React + Vite, with MapLibre GL JS and an appropriately attributed OpenStreetMap
basemap. Export compact, versioned, public-data artifacts from Python/DuckDB;
keep the large analytical database on the analysis side. One persistent map
instance receives scene state from an intersection observer. Put the story text
in structured content separate from map rendering and data transforms.

Verify desktop and mobile scrolling, reverse scrolling, keyboard navigation,
reduced motion, search, missing-data states, source links and map attribution.

## Visual-reference status

Every Neuron was opened and visually inspected: white background, a dominant
scientific visualization, restrained text and ample space. The NYT reference was
blocked by browser security policy. No workaround was attempted. The user was
asked whether to continue with Every Neuron and their written NYT direction.
The user approved proceeding without the blocked reference. An original React,
Vite and MapLibre prototype now lives in `web/`, with locally served fonts and
map geometry. No NYT page image was generated or copied.

## Prototype corrections

The doubled populations were traced to the unsafe numeric Cadastre-to-INE
fallback when a manifest name did not match. The importer now omits unmatched
crosswalks, collapses identical footprints before allocation and rejects
conflicting duplicate building identities. A complete database regeneration
has not been run.

The read-only web export excludes suspect legacy assignments and collapses
identical building rows before joining. It has 1,827 usable municipality results
and 421 unavailable/review results. Aggregated coverage is weighted by official
municipal population. The final scenes use explicitly labelled descriptive
rankings, not the unimplemented optimisation or disruption models.
