import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { colors, cleanName } from "./data";

const region = [
  [-7.15, 40.05],
  [-1.65, 43.3],
];
const collection = (features = []) => ({ type: "FeatureCollection", features });
const accessColors = [
  "interpolate",
  ["linear"],
  ["get", "coverage15"],
  0,
  colors.red,
  40,
  colors.orange,
  70,
  colors.yellow,
  100,
  colors.teal,
];

export function MapView({
  data,
  scene,
  selected,
  onSelect,
  city,
  footprints,
  supplemental = false,
}) {
  const container = useRef(null),
    instance = useRef(null),
    handlers = useRef({ onSelect });
  const [ready, setReady] = useState(0),
    [error, setError] = useState(false),
    [size, setSize] = useState("");
  handlers.current = { onSelect };
  const explorer = scene === 7;

  useEffect(() => {
    let map;
    try {
      map = new maplibregl.Map({
        container: container.current,
        center: [-4.7, 41.65],
        zoom: 6,
        style: {
          version: 8,
          sources: {},
          layers: [
            {
              id: "paper",
              type: "background",
              paint: { "background-color": "#f4f5f0" },
            },
          ],
        },
        attributionControl: false,
        dragRotate: false,
        pitchWithRotate: false,
      });
    } catch {
      setError(true);
      return;
    }
    instance.current = map;
    map.addControl(
      new maplibregl.AttributionControl({
        compact: true,
        customAttribution: "JCyL · © OpenStreetMap contributors · Catastro",
      }),
      "bottom-right",
    );
    map.addControl(
      new maplibregl.ScaleControl({ maxWidth: 85, unit: "metric" }),
      "bottom-left",
    );
    map.addControl(
      new maplibregl.NavigationControl({ showCompass: false }),
      "top-right",
    );
    map.scrollZoom.disable();
    map.doubleClickZoom.disable();
    map.touchZoomRotate.disableRotation();
    map.on("load", () => {
      for (const name of ["municipalities", "aeds", "leon", "roads"])
        map.addSource(name, { type: "geojson", data: data[name] });
      map.addSource("hospital-surface", {
        type: "image",
        url: `${import.meta.env.BASE_URL}data/hospital-times.png?v=${data.hospitalTimes.imageVersion}`,
        coordinates: data.hospitalTimes.coordinates,
      });
      map.addLayer({
        id: "hospital-surface",
        type: "raster",
        source: "hospital-surface",
        paint: { "raster-opacity": 0, "raster-fade-duration": 0 },
      });
      map.addSource("hospitals", {
        type: "geojson",
        data: data.hospitalTimes.hospitals,
      });
      for (const name of ["selected"])
        map.addSource(name, { type: "geojson", data: collection() });
      map.addLayer({
        id: "municipal-base",
        type: "circle",
        source: "municipalities",
        paint: {
          "circle-radius": 2.4,
          "circle-color": "#cbd2c8",
          "circle-opacity": 0.55,
        },
      });
      map.addLayer({
        id: "roads",
        type: "line",
        source: "roads",
        paint: {
          "line-color": "#9ca7a0",
          "line-width": ["interpolate", ["linear"], ["zoom"], 5, 0.55, 10, 1.6],
          "line-opacity": 0,
        },
      });
      map.addLayer({
        id: "municipal-access",
        type: "circle",
        source: "municipalities",
        filter: ["==", ["get", "status"], "available"],
        paint: {
          "circle-radius": 3.4,
          "circle-color": accessColors,
          "circle-opacity": 0,
          "circle-stroke-color": "#f7f7f2",
          "circle-stroke-width": 0.35,
        },
      });
      map.addLayer({
        id: "municipal-missing",
        type: "circle",
        source: "municipalities",
        filter: ["!=", ["get", "status"], "available"],
        paint: {
          "circle-radius": 3.5,
          "circle-color": "#f4f5f0",
          "circle-opacity": 0,
          "circle-stroke-color": "#8c9890",
          "circle-stroke-width": 1,
          "circle-stroke-opacity": 0,
        },
      });
      map.addLayer({
        id: "leon-buildings",
        type: "fill",
        source: "leon",
        paint: {
          "fill-opacity": 0,
          "fill-color": [
            "case",
            ["==", ["get", "minutes"], null],
            colors.red,
            [
              "interpolate",
              ["linear"],
              ["get", "minutes"],
              0,
              colors.teal,
              5,
              colors.yellow,
              10,
              colors.orange,
              15,
              colors.red,
            ],
          ],
        },
      });
      map.addLayer({
        id: "leon-outlines",
        type: "line",
        source: "leon",
        paint: {
          "line-color": "#49695f",
          "line-width": [
            "interpolate",
            ["linear"],
            ["zoom"],
            11,
            0.25,
            16,
            0.9,
          ],
          "line-opacity": 0,
        },
      });
      map.addLayer({
        id: "hospitals",
        type: "circle",
        source: "hospitals",
        paint: {
          "circle-radius": 6,
          "circle-color": "#faf9f6",
          "circle-stroke-color": "#253f43",
          "circle-stroke-width": 2,
          "circle-opacity": 0,
          "circle-stroke-opacity": 0,
        },
      });
      map.addLayer({
        id: "aeds",
        type: "circle",
        source: "aeds",
        paint: {
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["zoom"],
            5,
            2.5,
            8,
            3.8,
            13,
            5.4,
          ],
          "circle-color": colors.red,
          "circle-opacity": 0.75,
          "circle-stroke-color": "#fff",
          "circle-stroke-width": 0.5,
        },
      });
      map.addSource("regional-boundary", {
        type: "geojson",
        data: "/maps/castilla-y-leon.geojson",
        attribution:
          "Límite autonómico: SIU / Ministerio de Vivienda y Agenda Urbana",
      });
      map.addLayer({
        id: "regional-boundary-halo",
        type: "line",
        source: "regional-boundary",
        paint: {
          "line-color": "#faf9f6",
          "line-width": 3.8,
          "line-opacity": 0.8,
        },
      });
      map.addLayer({
        id: "regional-boundary",
        type: "line",
        source: "regional-boundary",
        paint: {
          "line-color": "#435d57",
          "line-width": 1.5,
          "line-opacity": 0.9,
        },
      });
      map.addLayer({
        id: "selected",
        type: "circle",
        source: "selected",
        paint: {
          "circle-radius": 16,
          "circle-color": "transparent",
          "circle-stroke-color": colors.ink,
          "circle-stroke-width": 1.7,
        },
      });
      map.addLayer({
        id: "municipal-hit",
        type: "circle",
        source: "municipalities",
        paint: { "circle-radius": 10, "circle-opacity": 0 },
      });
      const capitalIds = [
        "24089",
        "09059",
        "34120",
        "47186",
        "49275",
        "37274",
        "05019",
        "40194",
        "42173",
      ];
      for (const feature of data.municipalities.features.filter((f) =>
        capitalIds.includes(f.properties.id),
      )) {
        const label = document.createElement("span");
        label.className = "map-city";
        label.textContent = cleanName(feature.properties.name);
        new maplibregl.Marker({ element: label, anchor: "top", offset: [0, 8] })
          .setLngLat(feature.geometry.coordinates)
          .addTo(map);
      }
      map.on("click", "municipal-hit", (event) => {
        const { onSelect: select } = handlers.current;
        const feature = data.municipalities.features.find(
          (f) => f.properties.id === event.features[0].properties.id,
        );
        select(feature);
      });
      setReady((value) => value + 1);
    });
    const observer = new ResizeObserver(([entry]) => {
      map.resize();
      setSize(`${entry.contentRect.width}:${entry.contentRect.height}`);
    });
    observer.observe(container.current);
    return () => {
      observer.disconnect();
      map.remove();
      instance.current = null;
    };
  }, [data]);

  useEffect(() => {
    const map = instance.current;
    if (!ready || !map || !map.getSource("selected")) return;
    const duration = window.matchMedia("(prefers-reduced-motion: reduce)")
      .matches
      ? 0
      : 1200;
    const paint = (layer, property, value) => {
      map.setPaintProperty(layer, `${property}-transition`, {
        duration: duration / 2,
      });
      map.setPaintProperty(layer, property, value);
    };
    const detail = scene === 5 || (explorer && Boolean(city));
    for (const layer of [
      "municipal-base",
      "municipal-access",
      "municipal-missing",
      "aeds",
    ]) {
      map.setLayoutProperty(
        layer,
        "visibility",
        scene === 6 ? "none" : "visible",
      );
    }
    paint("hospital-surface", "raster-opacity", scene === 6 ? 0.82 : 0);
    paint("hospitals", "circle-opacity", scene === 6 ? 1 : 0);
    paint("hospitals", "circle-stroke-opacity", scene === 6 ? 1 : 0);
    const mobile = window.matchMedia("(max-width: 700px)").matches;
    const padding =
      mobile && !supplemental
        ? {
            top: 64,
            bottom: Math.round(container.current.clientHeight * 0.52),
            left: 15,
            right: 15,
          }
        : { top: 60, bottom: 55, left: 22, right: 22 };
    const coverage = scene === 4 || explorer;
    paint(
      "municipal-base",
      "circle-opacity",
      scene === 6 || explorer ? 0 : detail ? 0.1 : 0.5,
    );
    paint(
      "roads",
      "line-opacity",
      scene === 3 ? 0.85 : detail ? 0.4 : scene > 2 ? 0.24 : 0.14,
    );
    paint(
      "municipal-access",
      "circle-opacity",
      explorer
        ? ["interpolate", ["linear"], ["zoom"], 10, 1, 12, detail ? 0 : 1]
        : coverage && !detail
          ? 0.95
          : 0,
    );
    map.setFilter("municipal-access", [
      "all",
      ["==", ["get", "status"], "available"],
    ]);
    paint(
      "municipal-missing",
      "circle-opacity",
      explorer
        ? ["interpolate", ["linear"], ["zoom"], 10, 1, 12, detail ? 0 : 1]
        : 0,
    );
    paint(
      "municipal-missing",
      "circle-stroke-opacity",
      explorer
        ? ["interpolate", ["linear"], ["zoom"], 10, 1, 12, detail ? 0 : 1]
        : 0,
    );
    paint("leon-buildings", "fill-opacity", detail ? 0.82 : 0);
    paint("leon-outlines", "line-opacity", detail ? 0.7 : 0);
    paint(
      "aeds",
      "circle-opacity",
      scene < 3
        ? scene === 0
          ? 0.45
          : 0.85
        : detail
          ? 1
          : scene === 3
            ? 0.8
            : scene === 7
              ? 0.85
              : 0.05,
    );
    map.setPaintProperty(
      "aeds",
      "circle-color",
      detail || explorer ? colors.ink : colors.red,
    );
    map
      .getSource("selected")
      .setData(collection(explorer && selected ? [selected] : []));
    map.dragPan[explorer ? "enable" : "disable"]();
    map.touchZoomRotate[explorer ? "enable" : "disable"]();
    // Page scrolling must not change the map camera. Use buttons or pinch.
    map.scrollZoom.disable();
    const regionalCamera = map.cameraForBounds(region, { padding });
    map.setMinZoom(explorer ? (regionalCamera?.zoom ?? 5) : 0);
    map.doubleClickZoom[explorer ? "enable" : "disable"]();
    map.keyboard[explorer ? "enable" : "disable"]();
    map.boxZoom[explorer ? "enable" : "disable"]();
    if (detail)
      map.flyTo({
        center: city?.center ||
          selected?.geometry.coordinates || [-5.567, 42.6],
        zoom: 14.2,
        padding,
        duration,
        essential: false,
      });
    else if (explorer && selected)
      map.flyTo({
        center: selected.geometry.coordinates,
        zoom: 9.2,
        padding,
        duration,
        essential: false,
      });
    else {
      // fitBounds computes a padded camera but retains padding from earlier flyTo calls.
      map.setPadding({ top: 0, bottom: 0, left: 0, right: 0 });
      map.fitBounds(region, { padding, duration });
    }
  }, [data, ready, scene, selected, size, city, supplemental]);

  useEffect(() => {
    const source = instance.current?.getSource("leon");
    if (source) source.setData(footprints || collection());
  }, [ready, footprints]);

  return (
    <div
      className={`map-canvas ${explorer ? "is-explorable" : "is-story-locked"}`}
      ref={container}
      role="img"
      aria-label="Mapa de Castilla y León con registros DESA y acceso municipal. Las cifras también están disponibles en el relato y el buscador."
    >
      {error && (
        <div className="map-error">
          El mapa necesita WebGL. Puedes seguir leyendo el relato y consultar
          los municipios abajo.
        </div>
      )}
    </div>
  );
}
