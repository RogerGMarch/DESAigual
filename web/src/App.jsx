import {
  UncoveredPopulation,
  PopulationChart,
  CoverageChart,
  AccessScatter,
  CityComparison,
} from "./StoryCharts";
import { useEffect, useRef, useState } from "react";
import { DefibrillatorIntro } from "./DefibrillatorIntro";
import { MapView } from "./MapView";
import {
  loadData,
  populationGroups,
  accessPopulationGroups,
  formatNumber as num,
  formatPercent as pct,
  cleanName,
  searchMunicipalities,
} from "./data";

function Metric({ value, label }) {
  return (
    <div className="metric">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}
function Legend({ scene, hospitalTimes }) {
  if (scene === 5 || scene === 6) {
    const hospital = scene === 6;
    const maximum = hospital ? hospitalTimes.maximum : 15;
    return (
      <div className="legend">
        <span className="legend-title">
          {hospital
            ? "En coche al hospital de urgencias"
            : "A pie desde cada edificio al DESA"}
        </span>
        <div className="continuous-scale" />
        <div className="continuous-ticks">
          <span>0</span>
          <span>{Math.round(maximum / 3)}</span>
          <span>{Math.round((maximum * 2) / 3)}</span>
          <span>{hospital ? `${pct(maximum)} min` : ">15 min"}</span>
        </div>
        <small>
          {hospital
            ? "○ Hospital · superficie aproximada"
            : "Rojo: >15 min / sin ruta encontrada"}
        </small>
      </div>
    );
  }
  if ([4, 7].includes(scene))
    return (
      <div className="legend">
        <span className="legend-title">Población con acceso hasta 15 min</span>
        <div className="legend-scale">
          <span>0%</span>
          <i className="swatch red" />
          <i className="swatch orange" />
          <i className="swatch yellow" />
          <i className="swatch teal" />
          <span>100%</span>
        </div>
        <small>
          <i className="swatch hollow" /> Sin cálculo de acceso disponible
        </small>
      </div>
    );
  return (
    <div className="legend">
      <span className="legend-title">La red registrada</span>
      <div>
        <i className="swatch red" /> Registro DESA geolocalizado
      </div>
      <small>
        <i className="swatch gray" /> Municipio
      </small>
    </div>
  );
}
function AppContent({ data }) {
  const [scene, setScene] = useState(0),
    [selected, setSelected] = useState(null);
  const [query, setQuery] = useState(""),
    [searchOpen, setSearchOpen] = useState(false);
  const [progress, setProgress] = useState(0);
  const root = useRef(null),
    s = data.summary;
  const leon = data.municipalities.features.find(
    (f) => f.properties.id === "24089",
  ).properties;
  const [hospitalOpen, setHospitalOpen] = useState(false);
  const explorer = scene === 9;
  const mapScene = explorer ? 7 : [0, 1, 2, 4, 4, 5, 5, 4, 4][scene];
  const ponferrada = data.municipalities.features.find(
    (f) => f.properties.id === "24115",
  ).properties;
  const groups = populationGroups(data.municipalities.features);
  const accessGroups = accessPopulationGroups(data.municipalities.features);
  const outside = accessGroups.reduce((sum, g) => sum + g.outside, 0);
  const smallShare =
    (100 * accessGroups.slice(0, 3).reduce((sum, g) => sum + g.outside, 0)) /
    outside;
  const unknownPopulation = s.population - s.modeledPopulation;
  const cityId =
    scene === 5
      ? "24089"
      : scene === 6
        ? "24115"
        : explorer
          ? selected?.properties.id
          : null;
  const city = data.cities[cityId];
  const cityCache = useRef(new Map([["24089", data.leon]]));
  const [cityLayer, setCityLayer] = useState({
    id: "24089",
    geometry: data.leon,
  });
  useEffect(() => {
    if (!city) return;
    const controller = new AbortController();
    const cached = cityCache.current.get(cityId);
    if (cached) {
      setCityLayer({ id: cityId, geometry: cached });
    } else {
      setCityLayer({ id: cityId, loading: true });
      fetch(`${import.meta.env.BASE_URL}data/${city.file}`, {
        signal: controller.signal,
      })
        .then((response) => {
          if (!response.ok) throw new Error("City layer unavailable");
          return response.json();
        })
        .then((geometry) => {
          if (controller.signal.aborted) return;
          cityCache.current.set(cityId, geometry);
          setCityLayer({ id: cityId, geometry });
        })
        .catch((error) => {
          if (error.name !== "AbortError")
            setCityLayer({ id: cityId, error: true });
        });
    }
    return () => controller.abort();
  }, [cityId, city]);
  const matches = searchMunicipalities(data.municipalities.features, query);
  useEffect(() => {
    let frame;
    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const sections = [...root.current.querySelectorAll("[data-scene]")];
        const line = window.innerHeight * 0.52;
        let current = 0;
        for (const element of sections)
          if (element.getBoundingClientRect().top <= line)
            current = Number(element.dataset.scene);
        setScene(current);
        const height =
          document.documentElement.scrollHeight - window.innerHeight;
        setProgress(height ? window.scrollY / height : 0);
      });
    };
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    update();
    return () => {
      window.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
      cancelAnimationFrame(frame);
    };
  }, []);
  function choose(feature) {
    setSelected(feature);
    setQuery(cleanName(feature.properties.name));
    setSearchOpen(false);
  }
  const scenes = [
    {
      hero: true,
      kicker: "Análisis · Castilla y León",
      title: "Dónde vives cambia tu acceso a un desfibrilador",
      body: "Cruzamos desfibriladores, calles y edificios para saber a cuántas personas llega la red en Castilla y León. Los datos muestran diferencias entre municipios y nos permiten ver dónde se concentra la población con peor acceso.",
    },
    {
      kicker: "01 / Registro",
      title: `${num(s.registryRecords)} registros de desfibriladores`,
      body: `Empezamos por situar ${num(s.mappedRecords)} registros en el mapa. Después recorremos las calles desde los edificios residenciales hasta el desfibrilador más cercano. Así pasamos de contar dispositivos a estimar cuántas personas pueden llegar a ellos a pie.`,
      extra: (
        <p className="note">
          El acceso también depende de que el dispositivo esté disponible cuando
          se necesita. El European Resuscitation Council recomienda que los DESA
          de acceso público estén disponibles las 24 horas.{" "}
          <a href="#ref-erc">[1]</a>
        </p>
      ),
    },
    {
      chart: true,
      kicker: "02 / Población",
      title: `El ${pct(groups[0].towns + groups[1].towns)}% de los municipios tiene menos de 500 habitantes`,
      body: `En ellos vive el ${pct(groups[0].people + groups[1].people)}% de la población. Los ${groups[5].count} municipios de 50.000 habitantes o más concentran el ${pct(groups[5].people)}%. Para entender a quién llega la red, necesitamos mirar ambas cosas: cómo se reparte el territorio y dónde vive la gente.`,
      extra: <PopulationChart groups={groups} />,
    },
    {
      chart: true,
      kicker: "03 / Acceso a pie",
      title: `Un ${pct(100 - s.coverage[2])}% de la población analizada queda fuera del umbral de quince minutos`,
      body: `Son unas ${num(Math.round(outside / 1000) * 1000)} personas para las que el modelo no encuentra un desfibrilador en hasta quince minutos a pie. El gráfico muestra cómo cambia el alcance de la red al pasar de cinco a diez y a quince minutos. Ahora podemos ver dónde se concentra ese ${pct(100 - s.coverage[2])}%.`,
      extra: <CoverageChart summary={s} />,
    },
    {
      chart: true,
      kicker: "04 / Población fuera del umbral",
      title: `El ${pct(smallShare)}% de la población fuera del umbral vive en municipios de menos de 10.000 habitantes`,
      body: "La mayor parte de la población que queda fuera de esos quince minutos vive en municipios pequeños y medianos. Al agrupar los resultados por tamaño de municipio, aparece una desigualdad que el porcentaje regional deja en segundo plano.",
      extra: (
        <>
          <UncoveredPopulation groups={accessGroups} />
          <details className="editorial-detail">
            <summary>
              Ver la relación entre población municipal y acceso a cinco minutos
            </summary>
            <AccessScatter features={data.municipalities.features} />
          </details>
        </>
      ),
    },
    {
      kicker: "05 / Edificios · León",
      title: `León: ${pct(leon.coverage15)}% con acceso en hasta quince minutos`,
      body: "Bajamos a la escala de las calles. En León, la red alcanza a casi toda la población dentro de los quince minutos, pero el recorrido cambia de un edificio a otro. Cada huella del mapa muestra ese tiempo a pie.",
      extra: (
        <>
          <Metric
            value={num(leon.buildings)}
            label="edificios residenciales analizados"
          />
          <p className="note">
            Edificios del Catastro · población estimada. En rojo, recorridos de
            más de quince minutos y edificios sin ruta calculada.
          </p>
        </>
      ),
    },
    {
      kicker: "06 / Edificios · Ponferrada",
      title: `Ponferrada: ${pct(ponferrada.coverage15)}% con acceso en hasta quince minutos`,
      body: "En Ponferrada, el alcance baja a alrededor de dos de cada tres habitantes. Mantenemos la escala y los colores de León para ver cómo se distribuye el acceso entre sus edificios.",
      extra: (
        <>
          <Metric
            value={num(ponferrada.buildings)}
            label="edificios residenciales analizados"
          />
          <p className="note">
            Cobertura estimada para todo el municipio. Puedes recorrer todos los
            edificios al final, en el explorador.
          </p>
        </>
      ),
    },
    {
      chart: true,
      kicker: "07 / Comparación de las dos ciudades",
      title: `La diferencia a cinco minutos es de ${pct(leon.coverage5 - ponferrada.coverage5)} puntos porcentuales`,
      body: `A cinco minutos a pie, la red alcanza al ${pct(leon.coverage5)}% de la población de León y al ${pct(ponferrada.coverage5)}% de la de Ponferrada. Ampliar el recorrido mejora el acceso en ambas, pero la distancia entre las dos ciudades sigue siendo visible.`,
      extra: <CityComparison leon={leon} ponferrada={ponferrada} />,
    },
    {
      chart: true,
      kicker: "08 / Qué muestran los resultados",
      title: "Evaluar la red desde las personas",
      body: "El lugar de residencia marca diferencias en el acceso a un desfibrilador. Este mapa las hace visibles: permite localizar a la población con peor acceso y orientar la revisión de la red hacia esos lugares.",
      extra: (
        <div className="conclusion-evidence">
          <p>
            <strong>Mirar a quién llega la red.</strong> El total de
            dispositivos es el punto de partida. Los recorridos desde los
            edificios muestran qué población tiene uno cerca y dónde se acumulan
            las distancias.
          </p>
          <p>
            <strong>Comprobar que se pueda utilizar.</strong> Un dispositivo
            cercano debe estar accesible cuando se necesita. Los estudios de
            Copenhague y Gran Bretaña refuerzan la importancia de incorporar los
            horarios a la evaluación del acceso. <a href="#ref-karlsson">[2]</a>{" "}
            <a href="#ref-burgoine">[3]</a>
          </p>
          <p>
            <strong>Revisar la red con una perspectiva territorial.</strong> En
            España ya se han documentado diferencias de dotación entre
            comunidades autónomas. Aquí miramos dentro de Castilla y León,
            municipio a municipio, para que la cobertura regional no deje esas
            diferencias fuera de la conversación. <a href="#ref-spain">[4]</a>
          </p>
        </div>
      ),
    },
  ];
  return (
    <div ref={root}>
      <a href="#explorar" className="skip-link">
        Saltar al explorador
      </a>
      <header className="masthead">
        <a href="#inicio" className="wordmark">
          DESA<span>igual</span>
          <i />
        </a>
        <span className="masthead-middle">
          CASTILLA Y LEÓN · DATOS ABIERTOS
        </span>
        <a className="explore-link" href="#explorar">
          Explora los datos <span aria-hidden="true">↗</span>
        </a>
        <div
          className="reading-progress"
          style={{ width: `${progress * 100}%` }}
        />
      </header>
      <main>
        <div className={`scrolly ${explorer ? "is-explorer" : ""}`}>
          <div className={`map-stage ${scene === 0 ? "has-intro" : ""}`}>
            <DefibrillatorIntro active={scene === 0} />
            <div className="map-heading">
              <span>CASTILLA Y LEÓN</span>
              <span>{!explorer ? "ACCESO ESTIMADO" : "EXPLORA LOS DATOS"}</span>
            </div>
            <MapView
              data={data}
              scene={mapScene}
              city={city}
              footprints={
                city && cityLayer.id === cityId ? cityLayer.geometry : null
              }
              selected={selected}
              onSelect={(feature) => explorer && choose(feature)}
            />
            <Legend
              hospitalTimes={data.hospitalTimes}
              scene={city ? 5 : mapScene}
            />
            <span className="map-chapter">
              {String(Math.min(scene + 1, scenes.length)).padStart(2, "0")}
              <span> / {scenes.length}</span>
            </span>
          </div>
          <div className="story-steps">
            {scenes.map((step, i) => (
              <section
                className={`story-step ${step.hero ? "hero" : ""} ${step.chart ? "chart-step" : ""} ${scene === i ? "active" : ""}`}
                id={i === 0 ? "inicio" : `escena-${i}`}
                data-scene={i}
                key={i}
              >
                <div className="step-content">
                  <p className="eyebrow">{step.kicker}</p>
                  {step.hero ? <h1>{step.title}</h1> : <h2>{step.title}</h2>}
                  <p className="story-body">{step.body}</p>
                  {step.extra}
                  {!step.chart &&
                    !step.hero &&
                    city &&
                    (!cityLayer.geometry || cityLayer.id !== cityId) && (
                      <p className="note" role="status">
                        {cityLayer.error
                          ? "No se pudieron cargar los edificios. Recarga la página para reintentar."
                          : "Cargando edificios…"}
                      </p>
                    )}
                  {step.hero && (
                    <>
                      <div className="hero-meta">
                        <span>ANÁLISIS DE DATOS ABIERTOS</span>
                        <span>Lectura · 4 minutos</span>
                      </div>
                      <a className="scroll-prompt" href="#escena-1">
                        <span aria-hidden="true">↓</span> Continuar leyendo
                      </a>
                      <p className="version-note">
                        Versión de trabajo · septiembre de 2026
                      </p>
                    </>
                  )}
                </div>
              </section>
            ))}
            <section className="explorer-section" data-scene="9" id="explorar">
              <div className="explorer-content">
                <p className="eyebrow">EXPLORADOR MUNICIPAL</p>
                <h2>Consulta tu municipio</h2>
                <p>
                  Ahora puedes mover el mapa, ampliar y buscar un municipio para
                  consultar sus datos.
                </p>
                <div className="search">
                  <label htmlFor="municipality-search">Municipio</label>
                  <input
                    id="municipality-search"
                    type="search"
                    autoComplete="off"
                    placeholder="Por ejemplo, León"
                    value={query}
                    onFocus={() => setSearchOpen(true)}
                    onChange={(event) => {
                      setQuery(event.target.value);
                      setSearchOpen(true);
                    }}
                    onKeyDown={(event) => {
                      if (event.key === "Escape") setSearchOpen(false);
                      if (event.key === "Enter" && matches.length) {
                        choose(matches[0]);
                      }
                    }}
                    aria-expanded={searchOpen}
                    aria-controls="search-results"
                  />
                  {searchOpen && (
                    <ul id="search-results" className="search-results">
                      {matches.map((f) => (
                        <li key={f.properties.id}>
                          <button
                            onClick={() => {
                              choose(f);
                            }}
                          >
                            {cleanName(f.properties.name)}
                            <span>
                              {data.cities[f.properties.id]
                                ? "Edificios disponibles"
                                : f.properties.id}
                            </span>
                          </button>
                        </li>
                      ))}
                      {!matches.length && (
                        <li className="no-results">
                          No encontramos ese municipio.
                        </li>
                      )}
                    </ul>
                  )}
                </div>
                {selected ? (
                  <MunicipalityDetails feature={selected} />
                ) : (
                  <div className="explorer-empty">
                    <span>{num(s.municipalities)}</span>
                    <p>municipios en la base de datos.</p>
                    <small>
                      Puedes buscarlos por nombre o seleccionarlos en el mapa.
                    </small>
                  </div>
                )}
                {selected && explorer && !city && (
                  <p className="note">
                    El detalle por edificios todavía no está disponible para
                    este municipio.
                  </p>
                )}
                {selected && explorer && city && (
                  <p className="note" role="status">
                    {cityLayer.id !== cityId || cityLayer.loading
                      ? "Cargando edificios…"
                      : cityLayer.error
                        ? "No se pudieron cargar los edificios. Vuelve a toda la comunidad y selecciona el municipio para reintentar."
                        : `${num(city.buildings)} edificios residenciales · ${city.source}. Color: tiempo a pie al DESA.`}
                  </p>
                )}
                {selected && (
                  <button
                    className="text-button"
                    onClick={() => {
                      setSelected(null);
                      setQuery("");
                    }}
                  >
                    Volver a toda la comunidad
                  </button>
                )}
              </div>
            </section>
          </div>
        </div>
        <section className="complementary-analysis">
          <details
            onToggle={(event) => setHospitalOpen(event.currentTarget.open)}
          >
            <summary>
              Análisis complementario: tiempo en coche hasta un hospital con
              urgencias
            </summary>
            <p>
              Esta medida describe la distancia a la red hospitalaria y se
              calcula por separado del acceso a DESA. Se asigna a cada zona el
              tiempo del nodo viario con ruta al hospital más cercano, entre{" "}
              {data.hospitalTimes.hospitals.features.length} destinos. Es una
              aproximación espacial, no un tiempo de respuesta sanitaria ni un
              trayecto calculado desde cada parcela.
            </p>
            {hospitalOpen && (
              <div className="complementary-map">
                <MapView
                  data={data}
                  scene={6}
                  selected={null}
                  onSelect={() => {}}
                  supplemental
                />
                <Legend scene={6} hospitalTimes={data.hospitalTimes} />
              </div>
            )}
          </details>
        </section>
        <section className="methodology" id="metodologia">
          <div className="method-title">
            <p className="eyebrow">DE DÓNDE SALE ESTA HISTORIA</p>
            <h2>Fuentes y método</h2>
            <p>
              Resultados provisionales. Estas son las fuentes, las decisiones de
              cálculo y las limitaciones del análisis.
            </p>
          </div>
          <div className="method-body">
            <details className="references" open>
              <summary>Referencias científicas</summary>
              <ol>
                <li id="ref-erc">
                  <a
                    href="https://www.erc.edu/media/wrhj5sye/gl2025-04-bls-e.pdf"
                    target="_blank"
                    rel="noreferrer"
                  >
                    European Resuscitation Council · Adult Basic Life Support
                    (2025)
                  </a>
                  . Recomendaciones de acceso público y disponibilidad las 24
                  horas.
                </li>
                <li id="ref-karlsson">
                  <a
                    href="https://doi.org/10.1016/j.resuscitation.2019.01.014"
                    target="_blank"
                    rel="noreferrer"
                  >
                    Karlsson et al. · Accesibilidad de DESA en Copenhague (2019)
                  </a>
                  . Asociación entre disponibilidad en el momento de la parada,
                  utilización y supervivencia; estudio observacional.
                </li>
                <li id="ref-burgoine">
                  <a
                    href="https://pubmed.ncbi.nlm.nih.gov/37640454/"
                    target="_blank"
                    rel="noreferrer"
                  >
                    Burgoine et al. · Localización y privación socioeconómica en
                    Gran Bretaña (2024; en línea, 2023)
                  </a>
                  . Diferencias en acceso 24/7 en Inglaterra y Escocia; el
                  patrón no fue uniforme entre países.
                </li>
                <li id="ref-spain">
                  <a
                    href="https://pubmed.ncbi.nlm.nih.gov/36906492/"
                    target="_blank"
                    rel="noreferrer"
                  >
                    Ballesteros-Peña et al. · Diferencias de dotación entre
                    comunidades autónomas (2023)
                  </a>
                  . Datos oficiales de 2021–2022; no mide tiempos desde
                  edificios.
                </li>
              </ol>
              <p>
                Estas referencias justifican la relevancia del análisis. Las
                cifras de Castilla y León proceden del modelo y las fuentes que
                se describen a continuación.
              </p>
            </details>
            <details open>
              <summary>Cómo calculamos e interpretamos el acceso</summary>
              <p>
                Acceso a pie sobre una red de OpenStreetMap, con una velocidad
                de 4,8 km/h. La población se distribuye por superficie entre los
                edificios residenciales del Catastro y de OpenStreetMap. En 19
                municipios sin edificios disponibles, se utiliza un punto de
                localización municipal de Nominatim. La búsqueda alcanza los 360
                minutos. Se excluyen componentes con menos de diez nodos y se
                conectan edificios y DESA a redes de al menos diez nodos, a un
                máximo de 500 metros. La revisión descartó 18 DESA del cálculo
                de acceso por estar asociados a fragmentos aislados; el mapa del
                registro conserva sus ubicaciones.
              </p>
              <p>
                Un registro no equivale necesariamente a un dispositivo único:
                puede haber ubicaciones repetidas. La población de cada edificio
                es una estimación a partir de su superficie, no un recuento de
                residentes. Los umbrales de cinco, diez y quince minutos
                permiten comparar recorridos; no son una recomendación
                sanitaria. El cálculo no incluye el viaje de vuelta ni el tiempo
                de utilizar el dispositivo.
              </p>
              <p>
                Describimos diferencias territoriales, sin atribuirles una causa
                ni estimar vidas salvadas. El tamaño municipal no equivale a una
                clasificación por ruralidad o renta.{" "}
                {unknownPopulation > 0
                  ? `${num(unknownPopulation)} personas viven en municipios sin cálculo disponible y quedan fuera de los porcentajes de acceso.`
                  : "Esta versión incorpora cálculos para todos los municipios."}
              </p>
              <p>
                No se han incorporado horarios de acceso a los dispositivos,
                tráfico ni tiempos de respuesta sanitaria. Este sitio es una
                herramienta de investigación, no un servicio de localización
                para emergencias.
              </p>
            </details>
            <details>
              <summary>Datos incompletos y correcciones del prototipo</summary>
              <p>
                {num(s.municipalitiesWithAccess)} de {num(s.municipalities)}{" "}
                municipios tienen resultados utilizables. Los demás aparecen sin
                cobertura calculada. Se han excluido cruces dudosos entre
                códigos de Catastro e INE; sus números no son intercambiables.
                También se eliminan filas de edificios idénticas antes de unir
                las tablas.
              </p>
              <p>
                Los porcentajes agregados ponderan la cobertura de cada
                municipio por su población oficial. La base de datos original se
                conserva intacta; las correcciones se aplican a la exportación
                de esta web.
              </p>
            </details>
            <details open>
              <summary>Fuentes y descarga</summary>
              <ul className="source-list">
                <li>
                  <a href="https://datosabiertos.jcyl.es/web/jcyl/risp/es/salud/desfibriladores_espacios_fisicos/1284786686472.csv">
                    Junta de Castilla y León · Registro DESA ↗
                  </a>
                </li>
                <li>
                  <a href="https://datosabiertos.jcyl.es/web/jcyl/risp/es/sector-publico/municipios/1284278782067.csv">
                    Junta de Castilla y León · Municipios y población ↗
                  </a>
                </li>
                <li>
                  <a href="https://download.geofabrik.de/europe/spain/castilla-y-leon.html">
                    OpenStreetMap / Geofabrik · Red viaria ↗
                  </a>
                </li>
                <li>
                  <a href="https://www.catastro.hacienda.gob.es/webinspire/index.html">
                    Dirección General del Catastro · Edificios INSPIRE ↗
                  </a>
                </li>
              </ul>
              <p className="note">
                Registro y municipios descargados el 7 de septiembre de 2026.
                Extracto OSM del 6 de septiembre de 2026. © Colaboradores de
                OpenStreetMap, ODbL. Edificios: Dirección General del Catastro;
                Edificios adicionales: OpenStreetMap; puntos municipales:
                Nominatim.
              </p>
              <a
                className="download-link"
                href="data/municipalities.geojson"
                download
              >
                Descargar datos municipales (GeoJSON) ↓
              </a>
              <a className="download-link" href="data/summary.json" download>
                Descargar ficha del análisis (JSON) ↓
              </a>
            </details>
          </div>
        </section>
        <section className="author-section" aria-labelledby="author-heading">
          <div>
            <p className="eyebrow">SOBRE EL AUTOR</p>
            <h2 id="author-heading">Roger González</h2>
          </div>
          <div className="author-bio">
            <p>
              Soy físico e investigador en sistemas complejos e inteligencia
              artificial. Trabajo como Urban Data Scientist en el Barcelona
              Supercomputing Center (BSC-CNS), desarrollando modelos de
              movilidad y gemelos digitales urbanos.
            </p>
            <p>
              También soy cofundador de Rampa, un proyecto que combina datos
              abiertos e inteligencia artificial para encontrar rutas urbanas
              más accesibles.
            </p>
            <a
              href="https://www.rampa.space/en/about"
              target="_blank"
              rel="noreferrer"
            >
              Más sobre mí en Rampa <span aria-hidden="true">↗</span>
            </a>
          </div>
        </section>
      </main>
      <footer>
        <a href="#inicio" className="wordmark">
          DESA<span>igual</span>
        </a>
        <span>CASTILLA Y LEÓN · PROTOTIPO 2026</span>
        <a href="#inicio">Volver al principio ↑</a>
      </footer>
    </div>
  );
}
function MunicipalityDetails({ feature }) {
  const p = feature.properties;
  return (
    <div className="municipality-details" aria-live="polite">
      <h3>{cleanName(p.name)}</h3>
      <p className="municipality-pop">
        {num(p.population)} habitantes <span>· INE {p.id}</span>
      </p>
      {p.status === "available" ? (
        <>
          <div className="local-metrics">
            {[5, 10, 15].map((threshold) => (
              <Metric
                key={threshold}
                value={`${pct(p[`coverage${threshold}`])}%`}
                label={`${threshold === 15 ? "bajo" : "hasta"} ${threshold} minutos`}
              />
            ))}
          </div>
          <p className="note">
            Población estimada con acceso a pie.{" "}
            {p.populationSource === "nominatim_point"
              ? "Estimación desde un punto municipal de Nominatim."
              : `${num(p.buildings)} edificios analizados · ${p.populationSource === "osm_fallback" ? "OpenStreetMap" : "Catastro"}.`}
          </p>
        </>
      ) : (
        <div className="missing-state">
          <strong>
            {p.status === "review"
              ? "Cálculo excluido por una incidencia en los datos"
              : "Sin cálculo de acceso disponible"}
          </strong>
          <p>
            {p.status === "review"
              ? "Hay incidencias al relacionar edificios, municipios y resultados entre las fuentes. Excluimos la estimación hasta resolverlas. No equivale a cobertura cero."
              : "Los datos de esta versión no permiten calcular un resultado completo para este municipio. No significa que no tenga desfibriladores ni que su cobertura sea cero."}
          </p>
        </div>
      )}
    </div>
  );
}
export function App() {
  const [data, setData] = useState(null),
    [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    loadData()
      .then((value) => active && setData(value))
      .catch((e) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, []);
  if (error)
    return (
      <main className="loading">
        <h1>No hemos podido abrir los datos.</h1>
        <p>{error}</p>
        <button onClick={() => window.location.reload()}>
          Volver a intentar
        </button>
      </main>
    );
  if (!data)
    return (
      <main className="loading">
        <span className="wordmark">DESAigual</span>
        <p>Preparando el mapa del territorio…</p>
      </main>
    );
  return <AppContent data={data} />;
}
