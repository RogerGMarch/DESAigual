export const formatNumber = (number) =>
  new Intl.NumberFormat("es-ES", { useGrouping: "always" }).format(
    Math.round(number),
  );
export const formatPercent = (number) =>
  new Intl.NumberFormat("es-ES", { maximumFractionDigits: 1 }).format(number);
export const cleanName = (name) =>
  name
    .toLocaleLowerCase("es")
    .replace(/(^|[\s-])\p{L}/gu, (c) => c.toLocaleUpperCase("es"))
    .replace(/\s(De|Del|La|Las|Los|El|Y)(?=\s)/g, (c) => c.toLowerCase());
export const normalize = (text) =>
  text
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
export const colors = {
  teal: "#418b80",
  yellow: "#d8ad5c",
  orange: "#cd825a",
  red: "#b34f40",
  ink: "#253f43",
  missing: "#a3aaa6",
};

export function searchMunicipalities(features, query) {
  const term = normalize(query.trim());
  const rank = (name) => (name === term ? 0 : name.startsWith(term) ? 1 : 2);
  return features
    .filter((f) => normalize(f.properties.name).includes(term))
    .sort(
      (a, b) =>
        rank(normalize(a.properties.name)) -
          rank(normalize(b.properties.name)) ||
        b.properties.population - a.properties.population ||
        a.properties.id.localeCompare(b.properties.id),
    )
    .slice(0, 7);
}

// Descriptive rankings, NOT a location-allocation solver or impact forecast.
export function rankCandidates(municipalities, aeds) {
  const uniqueSites = [
    ...new Map(
      aeds.features.map((f) => [
        f.geometry.coordinates.join(","),
        f.geometry.coordinates,
      ]),
    ).values(),
  ];
  const candidates = municipalities.features.filter(
    (f) => f.properties.status === "available" && f.properties.population > 0,
  );
  const spatial = new Map(
    candidates.map((feature) => {
      const [lon, lat] = feature.geometry.coordinates;
      let first = Infinity,
        second = Infinity;
      for (const [x, y] of uniqueSites) {
        const d =
          ((x - lon) * Math.cos((lat * Math.PI) / 180)) ** 2 + (y - lat) ** 2;
        if (d < first) {
          second = first;
          first = d;
        } else if (d < second) second = d;
      }
      return [feature.properties.id, Math.sqrt(second) * 111.2];
    }),
  );
  const tie = (a, b) => a.properties.id.localeCompare(b.properties.id);
  const unmet = (f) =>
    f.properties.population * (1 - f.properties.coverage15 / 100);
  return {
    population: [...candidates].sort(
      (a, b) => unmet(b) - unmet(a) || tie(a, b),
    ),
    equity: [...candidates].sort(
      (a, b) =>
        a.properties.coverage15 - b.properties.coverage15 ||
        a.properties.population - b.properties.population ||
        tie(a, b),
    ),
    spatial: [...candidates].sort(
      (a, b) =>
        spatial.get(b.properties.id) - spatial.get(a.properties.id) ||
        tie(a, b),
    ),
  };
}

export async function loadData() {
  const names = [
    "summary.json",
    "municipalities.geojson",
    "aeds.geojson",
    "leon.geojson",
    "roads.geojson",
    "hospital-times.json",
    "cities.json",
  ];
  const values = await Promise.all(
    names.map(async (name) => {
      const response = await fetch(`${import.meta.env.BASE_URL}data/${name}`, {
        cache: "no-cache",
      });
      if (!response.ok) throw new Error(`No se pudo cargar ${name}`);
      return response.json();
    }),
  );
  const [summary, municipalities, aeds, leon, roads, hospitalTimes, cities] =
    values;
  return {
    summary,
    municipalities,
    aeds,
    leon,
    roads,
    hospitalTimes,
    cities,
  };
}

export function populationGroups(features) {
  const bands = [
    [0, 100, "Menos de 100"],
    [100, 500, "100–499"],
    [500, 2000, "500–1.999"],
    [2000, 10000, "2.000–9.999"],
    [10000, 50000, "10.000–49.999"],
    [50000, Infinity, "50.000 o más"],
  ];
  const total = features.reduce((sum, f) => sum + f.properties.population, 0);
  return bands.map(([low, high, label]) => {
    const rows = features.filter(
      (f) => f.properties.population >= low && f.properties.population < high,
    );
    return {
      label,
      count: rows.length,
      towns: (100 * rows.length) / features.length,
      people:
        (100 * rows.reduce((sum, f) => sum + f.properties.population, 0)) /
        total,
    };
  });
}

export function accessPopulationGroups(features) {
  return [
    [0, 500, "Menos de 500"],
    [500, 2000, "500–1.999"],
    [2000, 10000, "2.000–9.999"],
    [10000, 50000, "10.000–49.999"],
    [50000, Infinity, "50.000 o más"],
  ].map(([low, high, label]) => {
    const group = { label, low, covered: 0, outside: 0, unknown: 0 };
    for (const { properties: p } of features) {
      if (p.population < low || p.population >= high) continue;
      if (p.status !== "available") group.unknown += p.population;
      else {
        group.covered += (p.population * p.coverage15) / 100;
        group.outside += p.population * (1 - p.coverage15 / 100);
      }
    }
    return group;
  });
}
