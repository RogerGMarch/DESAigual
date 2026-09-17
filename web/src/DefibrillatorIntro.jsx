import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";

// Original procedural AED: molded shell, rubber bumper and printed face details.
export function DefibrillatorIntro({ active }) {
  const host = useRef(null);
  const activeRef = useRef(active);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    activeRef.current = active;
  }, [active]);
  useEffect(() => {
    const element = host.current;
    setFailed(false);
    function disposeObject(root) {
      root.traverse((obj) => {
        obj.geometry?.dispose();
        const materials = obj.material
          ? Array.isArray(obj.material)
            ? obj.material
            : [obj.material]
          : [];
        materials.forEach((m) => {
          Object.values(m).forEach((value) => {
            if (value?.isTexture) value.dispose();
          });
          m.dispose();
        });
      });
    }
    let renderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      setFailed(true);
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));
    renderer.setClearColor(0x000000, 0);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;
    element.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(33, 1, 0.1, 100);
    camera.position.set(0, 0.15, 9.6);
    scene.add(new THREE.HemisphereLight(0xffffff, 0x82908b, 1.8));
    const key = new THREE.DirectionalLight(0xfff3df, 3);
    key.position.set(-3, 5, 7);
    scene.add(key);
    const rim = new THREE.DirectionalLight(0xc2e5e0, 2);
    rim.position.set(4, 2, -2);
    scene.add(rim);
    const device = new THREE.Group();
    scene.add(device);
    const white = new THREE.MeshStandardMaterial({
      color: 0xeceee8,
      roughness: 0.3,
    });
    const teal = new THREE.MeshStandardMaterial({
      color: 0x23564e,
      roughness: 0.64,
    });
    const dark = new THREE.MeshStandardMaterial({
      color: 0x233e3d,
      roughness: 0.5,
    });
    const orange = new THREE.MeshStandardMaterial({
      color: 0xeaa344,
      roughness: 0.33,
    });
    const mint = new THREE.MeshStandardMaterial({
      color: 0x96bc9b,
      roughness: 0.4,
    });
    function box(w, h, d, r, material, x, y, z) {
      const mesh = new THREE.Mesh(
        new RoundedBoxGeometry(w, h, d, 5, r),
        material,
      );
      mesh.position.set(x, y, z);
      device.add(mesh);
      return mesh;
    }
    box(2.85, 3.25, 0.88, 0.27, teal, 0, -0.08, 0);
    // A dark gasket separates the molded front from the protective bumper.
    box(2.78, 3.17, 0.65, 0.25, dark, 0, -0.04, 0.16);
    box(2.72, 3.1, 0.59, 0.24, white, 0, -0.04, 0.25);
    box(0.065, 1.25, 0.42, 0.025, dark, 1.395, -0.1, -0.01);
    for (let i = 0; i < 8; i++) {
      box(0.075, 0.035, 0.34, 0.012, teal, 1.435, -0.56 + i * 0.125, 0);
    }
    // Open carry handle: the three rounded bars leave a real gap.
    box(0.24, 0.62, 0.39, 0.1, teal, -0.77, 1.67, -0.04);
    box(0.24, 0.62, 0.39, 0.1, teal, 0.77, 1.67, -0.04);
    box(1.77, 0.25, 0.39, 0.1, teal, 0, 1.97, -0.04);
    box(1.2, 0.13, 0.405, 0.055, dark, 0, 1.95, -0.04);
    for (let i = 0; i < 9; i++)
      box(0.025, 0.14, 0.418, 0.009, teal, -0.48 + i * 0.12, 1.945, -0.04);
    box(2.26, 0.83, 0.05, 0.08, dark, 0, 0.77, 0.57);
    box(2.05, 0.61, 0.025, 0.04, mint, 0, 0.77, 0.61);
    function label(
      text,
      w,
      h,
      x,
      y,
      z,
      color = "#294842",
      size = 55,
      bg = null,
    ) {
      const canvas = document.createElement("canvas");
      canvas.width = 768;
      canvas.height = 192;
      const ctx = canvas.getContext("2d");
      if (bg) {
        ctx.fillStyle = bg;
        ctx.fillRect(0, 0, 768, 192);
      }
      ctx.fillStyle = color;
      ctx.font = `600 ${size}px Arial`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(text, 384, 96);
      const texture = new THREE.CanvasTexture(canvas);
      texture.colorSpace = THREE.SRGBColorSpace;
      const mesh = new THREE.Mesh(
        new THREE.PlaneGeometry(w, h),
        new THREE.MeshBasicMaterial({
          map: texture,
          transparent: true,
          depthWrite: false,
          toneMapped: false,
        }),
      );
      mesh.position.set(x, y, z);
      device.add(mesh);
    }
    label("DESA", 1.2, 0.3, 0, 1.35, 0.565, "#326e65", 65);
    // Sharp, emissive-free LCD graphic with an original trace.
    function decal(width, height, x, y, z, draw) {
      const canvas = document.createElement("canvas");
      canvas.width = 1024;
      canvas.height = Math.round((1024 * height) / width);
      const ctx = canvas.getContext("2d");
      draw(ctx, canvas.width, canvas.height);
      const texture = new THREE.CanvasTexture(canvas);
      texture.colorSpace = THREE.SRGBColorSpace;
      texture.anisotropy = Math.min(
        4,
        renderer.capabilities.getMaxAnisotropy(),
      );
      const mesh = new THREE.Mesh(
        new THREE.PlaneGeometry(width, height),
        new THREE.MeshBasicMaterial({
          map: texture,
          transparent: true,
          toneMapped: false,
          depthWrite: false,
        }),
      );
      mesh.position.set(x, y, z);
      device.add(mesh);
    }
    decal(1.96, 0.55, 0, 0.77, 0.64, (ctx, w, h) => {
      ctx.fillStyle = "#b9cab4";
      ctx.fillRect(0, 0, w, h);
      ctx.strokeStyle = "#839e8633";
      ctx.lineWidth = 1;
      for (let x = 0; x < w; x += 32) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();
      }
      for (let y = 0; y < h; y += 32) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.stroke();
      }
      ctx.fillStyle = "#294d45";
      ctx.font = "500 34px Arial";
      ctx.fillText("CADA MINUTO CUENTA", 38, 53);
      ctx.strokeStyle = "#2a574a";
      ctx.lineWidth = 8;
      ctx.lineJoin = "round";
      ctx.beginPath();
      [
        [40, 170],
        [210, 170],
        [250, 149],
        [284, 170],
        [352, 170],
        [381, 194],
        [411, 96],
        [443, 219],
        [474, 170],
        [570, 170],
        [613, 144],
        [660, 170],
        [960, 170],
      ].forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
      ctx.stroke();
      ctx.strokeRect(w - 92, 28, 52, 25);
      ctx.fillRect(w - 85, 34, 36, 13);
    });
    label("DESFIBRILADOR", 1.55, 0.32, 0, -1.28, 0.565, "#57726b", 43);
    box(
      2.21,
      1.11,
      0.035,
      0.1,
      new THREE.MeshStandardMaterial({ color: 0xcbd5c9, roughness: 0.65 }),
      0,
      -0.26,
      0.562,
    );
    decal(2.03, 0.97, 0, -0.26, 0.589, (ctx, w, h) => {
      ctx.fillStyle = "#e3e8de";
      ctx.fillRect(0, 0, w, h);
      ctx.strokeStyle = "#6f8b80";
      ctx.lineWidth = 9;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      // A torso and two electrode symbols, rendered as printed device artwork.
      ctx.beginPath();
      ctx.moveTo(416, 64);
      ctx.lineTo(413, 101);
      ctx.bezierCurveTo(390, 130, 321, 115, 296, 159);
      ctx.lineTo(277, 295);
      ctx.lineTo(337, 303);
      ctx.lineTo(354, 197);
      ctx.lineTo(353, 414);
      ctx.lineTo(669, 414);
      ctx.lineTo(670, 197);
      ctx.lineTo(690, 303);
      ctx.lineTo(750, 295);
      ctx.lineTo(730, 159);
      ctx.bezierCurveTo(704, 115, 635, 130, 612, 101);
      ctx.lineTo(609, 64);
      ctx.stroke();
      ctx.beginPath();
      ctx.ellipse(512, 65, 67, 62, 0, 0, Math.PI * 2);
      ctx.stroke();
      [
        [402, 182, -0.2],
        [622, 298, 0.2],
      ].forEach(([x, y, a]) => {
        ctx.save();
        ctx.translate(x, y);
        ctx.rotate(a);
        ctx.fillStyle = "#fafbf4";
        ctx.strokeStyle = "#4f7869";
        ctx.lineWidth = 6;
        ctx.beginPath();
        ctx.roundRect(-42, -55, 84, 110, 18);
        ctx.fill();
        ctx.stroke();
        ctx.restore();
      });
      ctx.strokeStyle = "#799489";
      ctx.lineWidth = 5;
      ctx.beginPath();
      ctx.moveTo(402, 130);
      ctx.bezierCurveTo(343, 45, 152, 52, 150, 177);
      ctx.bezierCurveTo(138, 414, 617, 470, 622, 355);
      ctx.stroke();
    });
    function button(x, y, material, radius) {
      const mesh = new THREE.Mesh(
        new THREE.CylinderGeometry(radius, radius, 0.08, 48),
        material,
      );
      mesh.rotation.x = Math.PI / 2;
      mesh.position.set(x, y, 0.62);
      device.add(mesh);
    }
    button(-0.58, -0.98, teal, 0.17);
    decal(0.23, 0.23, -0.58, -0.98, 0.666, (ctx, w, h) => {
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 65;
      ctx.lineCap = "round";
      ctx.beginPath();
      ctx.arc(w / 2, h / 2, w * 0.3, -Math.PI * 0.32, Math.PI * 1.32);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(w / 2, h * 0.11);
      ctx.lineTo(w / 2, h * 0.48);
      ctx.stroke();
    });
    button(0.55, -0.98, orange, 0.21);
    decal(0.25, 0.29, 0.55, -0.98, 0.668, (ctx, w, h) => {
      ctx.fillStyle = "#fff8df";
      ctx.beginPath();
      ctx.moveTo(w * 0.56, h * 0.06);
      ctx.lineTo(w * 0.19, h * 0.55);
      ctx.lineTo(w * 0.48, h * 0.55);
      ctx.lineTo(w * 0.36, h * 0.95);
      ctx.lineTo(w * 0.83, h * 0.38);
      ctx.lineTo(w * 0.56, h * 0.38);
      ctx.closePath();
      ctx.fill();
    });
    // Recessed fasteners and a small readiness indicator add physical scale.
    const metal = new THREE.MeshStandardMaterial({
      color: 0x8f9d96,
      metalness: 0.55,
      roughness: 0.38,
    });
    [
      [-1.12, 1.25],
      [1.12, 1.25],
      [-1.1, -1.3],
      [1.1, -1.3],
    ].forEach(([x, y]) => {
      const screw = new THREE.Mesh(
        new THREE.CylinderGeometry(0.037, 0.037, 0.014, 20),
        metal,
      );
      screw.rotation.x = Math.PI / 2;
      screw.position.set(x, y, 0.545);
      device.add(screw);
      box(0.035, 0.006, 0.006, 0.002, dark, x, y, 0.555);
    });
    box(
      0.105,
      0.045,
      0.023,
      0.018,
      new THREE.MeshStandardMaterial({
        color: 0x80b47c,
        emissive: 0x254d21,
        emissiveIntensity: 0.25,
        roughness: 0.25,
      }),
      0.86,
      1.32,
      0.558,
    );
    for (let i = 0; i < 5; i++)
      box(0.025, 0.18, 0.015, 0.008, dark, -0.15 + i * 0.07, -0.98, 0.569);
    const pointer = { x: 0, y: 0 };
    const move = (e) => {
      const rect = element.getBoundingClientRect();
      pointer.x = (e.clientX - rect.left) / rect.width - 0.5;
      pointer.y = (e.clientY - rect.top) / rect.height - 0.5;
    };
    const reset = () => {
      pointer.x = 0;
      pointer.y = 0;
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("blur", reset);
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const resize = () => {
      const { width, height } = element.getBoundingClientRect();
      if (!width || !height) return;
      renderer.setSize(width, height);
      camera.aspect = width / height;
      camera.position.z = camera.aspect < 0.85 ? 11.4 : 9.6;
      camera.updateProjectionMatrix();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    resize();
    let frame;
    let last = 0;
    function draw(time) {
      frame = requestAnimationFrame(draw);
      if (!activeRef.current || document.hidden || time - last < 32) return;
      last = time;
      const t = motion.matches ? 0 : time / 1000;
      device.rotation.set(
        -0.09 + (motion.matches ? 0 : pointer.y * 0.07),
        -0.28 +
          (motion.matches ? 0 : Math.sin(t * 0.4) * 0.07 + pointer.x * 0.13),
        -0.075,
      );
      device.position.y = motion.matches ? 0 : Math.sin(t * 0.8) * 0.055;
      renderer.render(scene, camera);
    }
    frame = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("pointermove", move);
      window.removeEventListener("blur", reset);
      disposeObject(scene);
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, []);
  return (
    <div
      className={`defib-intro ${active ? "is-visible" : ""}`}
      aria-hidden={!active}
    >
      <div className="defib-halo" />
      <div
        ref={host}
        className="defib-render"
        role="img"
        aria-label="Desfibrilador tridimensional blanco y verde, sobre un mapa desenfocado de Castilla y León"
      />
      {failed && (
        <div className="defib-fallback">
          <span>ϟ</span>
          <strong>DESA</strong>
          <small>Desfibrilador externo semiautomático</small>
        </div>
      )}
      <div className="defib-caption">
        <span>DESFIBRILADOR EXTERNO SEMIAUTOMÁTICO</span>
        <p>DESA</p>
        <small>Modelo 3D ilustrativo</small>
      </div>
    </div>
  );
}
