import { useEffect, useState } from "react";
import { formatNumber as num, formatPercent as pct, cleanName } from "./data";

export function PopulationChart({ groups }) {
  return (
    <figure className="population-graphic">
      <div className="population-head">
        <span>Habitantes por municipio</span>
        <span>Municipios</span>
        <span>Población</span>
      </div>
      {groups.map((g) => (
        <div className="population-row" key={g.label}>
          <span>{g.label}</span>
          {["towns", "people"].map((key) => (
            <div className={`distribution-bar ${key}`} key={key}>
              <i style={{ width: `${(g[key] / 55) * 100}%` }} />
              <b>{pct(g[key])}%</b>
            </div>
          ))}
        </div>
      ))}
      <figcaption>
        Distribución de los 2.248 municipios. Incluye los que no tienen un
        cálculo de acceso disponible.
      </figcaption>
    </figure>
  );
}
export function CoverageChart({ summary }) {
  return (
    <figure className="coverage-graphic">
      <div className="threshold-totals">
        {summary.coverage.map((value, i) => (
          <div key={i}>
            <strong>
              {pct(value)}
              <span>%</span>
            </strong>
            <p>
              {["Hasta 5 minutos", "Hasta 10 minutos", "Hasta 15 minutos"][i]}
            </p>
          </div>
        ))}
      </div>
      <div className="population-track">
        {summary.coverage.map((value, i) => (
          <div
            key={i}
            className={`access-segment segment-${i}`}
            style={{
              width: `${i === 0 ? value : value - summary.coverage[i - 1]}%`,
            }}
          />
        ))}
      </div>
      <div className="access-key">
        <span>
          <i className="segment-0" />
          Hasta 5 min
        </span>
        <span>
          <i className="segment-1" />
          Más de 5 y hasta 10 min
        </span>
        <span>
          <i className="segment-2" />
          Más de 10 y hasta 15 min
        </span>
        <span>
          <i style={{ background: "#b34f40" }} />
          &gt;15 min / sin ruta calculada · {pct(100 - summary.coverage[2])}%
        </span>
      </div>
      <figcaption>
        Los porcentajes superiores son acumulados. Estimaciones para{" "}
        {num(summary.municipalitiesWithAccess)} municipios (
        {num(summary.modeledPopulation)} habitantes), ponderadas por población.
        Quince minutos es el umbral de comparación. La búsqueda de rutas alcanza
        los 360 minutos. <a href="#metodologia">Fuentes y método</a>.
      </figcaption>
    </figure>
  );
}
export function AccessScatter({ features }) {
  const [small, setSmall] = useState(
    () => window.matchMedia("(max-width:700px)").matches,
  );
  useEffect(() => {
    const query = window.matchMedia("(max-width:700px)");
    const update = () => setSmall(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  const width = small ? 620 : 860;
  const bottom = small ? 370 : 280;
  const rows = features.filter(
    (f) => f.properties.status === "available" && f.properties.population > 0,
  );
  const x = (p) => 60 + (Math.log10(p) / 6) * (width - 100),
    y = (p) => bottom - p * ((bottom - 55) / 100);
  return (
    <figure className="scatter-graphic">
      <svg
        viewBox={`0 0 ${width} ${bottom + 70}`}
        role="img"
        aria-labelledby="scatter-title scatter-desc"
      >
        <title id="scatter-title">
          Población municipal y acceso a pie en cinco minutos
        </title>
        <desc id="scatter-desc">
          Un punto por municipio con datos utilizables. La población usa una
          escala logarítmica. León y Ponferrada se destacan para comparar sus
          resultados.
        </desc>
        {[0, 25, 50, 75, 100].map((v) => (
          <g key={v}>
            <line
              x1="60"
              x2={width - 40}
              y1={y(v)}
              y2={y(v)}
              stroke="#e7e7e7"
            />
            <text x="45" y={y(v) + 4} textAnchor="end">
              {v}%
            </text>
          </g>
        ))}
        {[10, 100, 1000, 10000, 100000].map((v) => (
          <g key={v}>
            <line x1={x(v)} x2={x(v)} y1="55" y2={bottom} stroke="#eeeeee" />
            <text x={x(v)} y={bottom + 30} textAnchor="middle">
              {num(v)}
            </text>
          </g>
        ))}
        <text x="60" y="24">
          Población con acceso en hasta 5 min
        </text>
        <text x={width / 2} y={bottom + 65} textAnchor="middle">
          Habitantes · escala logarítmica (×10 por intervalo)
        </text>
        {rows.map((f) => (
          <circle
            key={f.properties.id}
            cx={x(f.properties.population)}
            cy={y(f.properties.coverage5)}
            r="2.4"
            fill="#527c72"
            opacity=".24"
          />
        ))}
        {["24089", "24115"].map((id) => {
          const p = rows.find((f) => f.properties.id === id)?.properties;
          if (!p) return null;
          return (
            <g key={id}>
              <circle
                cx={x(p.population)}
                cy={y(p.coverage5)}
                r="5"
                fill="#b34f40"
              />
              <text
                x={x(p.population) + 10}
                y={y(p.coverage5) - 10}
                className="scatter-label"
              >
                {cleanName(p.name)}
              </text>
            </g>
          );
        })}
      </svg>
      <figcaption>
        {num(rows.length)} municipios con resultados utilizables;{" "}
        {num(features.length - rows.length)} quedan fuera porque el prototipo no
        dispone de un cálculo comparable:{" "}
        {num(features.filter((f) => f.properties.status === "missing").length)}{" "}
        por datos incompletos y{" "}
        {num(features.filter((f) => f.properties.status === "review").length)}{" "}
        por incidencias al cruzar las fuentes. No se les asigna cobertura cero.
        El eje vertical es lineal, de 0 a 100%; solo la población usa una escala
        logarítmica.
      </figcaption>
    </figure>
  );
}
export function CityComparison({ leon, ponferrada }) {
  return (
    <figure className="comparison-graphic">
      <div className="comparison-key">
        <span>● Hasta 5 minutos</span>
        <span>● Hasta 15 minutos</span>
      </div>
      {[leon, ponferrada].map((p) => (
        <div className="comparison-row" key={p.id}>
          <strong>{cleanName(p.name)}</strong>
          <div className="comparison-axis">
            <i
              style={{
                left: `${p.coverage5}%`,
                width: `${p.coverage15 - p.coverage5}%`,
              }}
            />
            <span
              className="comparison-point early"
              style={{ left: `${p.coverage5}%` }}
            >
              <b>{pct(p.coverage5)}%</b>
            </span>
            <span
              className="comparison-point late"
              style={{ left: `${p.coverage15}%` }}
            >
              <b>{pct(p.coverage15)}%</b>
            </span>
          </div>
        </div>
      ))}
      <div className="comparison-ticks">
        <span>0%</span>
        <span>50%</span>
        <span>100%</span>
      </div>
      <figcaption>
        Porcentaje de población estimada con acceso. Edificios del Catastro y la
        misma red de cálculo para ambas ciudades. Las líneas unen umbrales de
        tiempo, no fechas.
      </figcaption>
    </figure>
  );
}

export function UncoveredPopulation({ groups }) {
  const max = Math.max(...groups.map((g) => g.covered + g.outside + g.unknown));
  return (
    <figure className="uncovered-graphic">
      <div className="access-key">
        <span>
          <i style={{ background: "#418b80" }} />
          Con ruta hasta 15 min
        </span>
        <span>
          <i style={{ background: "#b34f40" }} />
          &gt;15 min / sin ruta calculada
        </span>
        <span>
          <i style={{ background: "#d9dcda" }} />
          Sin cálculo disponible
        </span>
      </div>
      <div className="uncovered-head">
        <span>Habitantes del municipio</span>
        <span>Población · misma escala en todas las filas</span>
        <span>&gt;15 min / sin ruta</span>
      </div>
      {groups.map((g) => (
        <div className="uncovered-row" key={g.label}>
          <span>{g.label}</span>
          <div className="uncovered-track">
            {["covered", "outside", "unknown"].map((k) => (
              <i
                key={k}
                className={`uncovered-${k}`}
                style={{ width: `${(100 * g[k]) / max}%` }}
              />
            ))}
          </div>
          <strong>≈ {num(g.outside)}</strong>
        </div>
      ))}
      <figcaption>
        Estimaciones de población a partir de los porcentajes municipales;
        cifras redondeadas. El porcentaje del titular se refiere a los
        resultados disponibles. En gris, población sin cálculo, excluida de ese
        porcentaje.
      </figcaption>
    </figure>
  );
}
