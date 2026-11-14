// Sagami Bay as one open world: renderer, camera, ground, water and sharks, driven by
// zustand(t). The camera pose is a pure function of the state, so ?t= always shows the same
// picture; only a viewer who drags the view takes over for a while.
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import gsap from "gsap";
import { CH1_INTRO_MS, CH1_STATION_MS, STATIONEN, type Blickpunkt, type Zustand } from "../lib/ablauf";
import { baueKueste } from "./kueste";
import { baueHintergrund, baueMeer } from "./meer";
import { ARTEN, baueHaie, neueAnsicht, STUFE_INDEX } from "./haie";
import { bodenY, Y_PER_M } from "./koordinaten";
import { NEBEL, wasserFarbe } from "./wasser";

/** On the model a highlighted LED alternates bright and dim every 400 ms (SPOT_BLINK_MS). */
const SPOT_BLINK_MS = 400;
/** fog density: close on the descent, so each station shows its own depth band; wide in the act */
const NEBEL_TOUR = 0.02;
const NEBEL_AKT = 0.0075;
/** the camera keeps this much water between itself and the ground (scene units) */
const BODEN_FREI = 1.5;
/** a viewer's drag holds the view this long before the tour takes it back (s) */
const FREI_S = 10;

interface Pose {
  pos: THREE.Vector3;
  ziel: THREE.Vector3;
  nebel: number;
}

export interface Szene {
  render(tSek: number, z: Zustand, gewaehlt: number | null): void;
  resize(): void;
  /** the shark nearest to a screen point (CSS pixels), within reach of a finger, or null */
  waehle(x: number, y: number): number | null;
  /** screen position in CSS pixels of a shark, or null when it is behind the camera */
  bildschirm(led: number): { x: number; y: number } | null;
}

const smooth = (f: number) => f * f * (3 - 2 * f);

export function baueSzene(canvas: HTMLCanvasElement): Szene {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(40, 1, 0.3, 8000);

  scene.add(baueHintergrund(), baueKueste(), baueMeer());
  const haie = baueHaie();
  scene.add(haie.group);

  // ---- the poses the tour moves between
  const station = (i: number): Pose => {
    const a = haie.ankerPos[STATIONEN[i] - 1];
    const seite = i % 2 ? 1 : -1;
    const pos = a.clone().add(new THREE.Vector3(seite * 7, 1.6, 26));
    // the shallowest station is filmed from just below the surface
    pos.y = Math.min(pos.y, -0.35);
    return { pos, ziel: a.clone(), nebel: NEBEL_TOUR };
  };
  const a0 = haie.ankerPos[STATIONEN[0] - 1];
  const oben: Pose = {
    pos: new THREE.Vector3(a0.x + 6, 2.4, a0.z + 40),
    ziel: new THREE.Vector3(a0.x - 2, 0.8, a0.z - 30),
    nebel: NEBEL_TOUR,
  };
  // the act: the whole slope with all depths at once, seen from the open sea
  const box = new THREE.Box3().setFromPoints(haie.ankerPos);
  const mitte = box.getCenter(new THREE.Vector3());
  const akt: Pose = {
    pos: new THREE.Vector3(mitte.x + 40, -28, box.max.z + 95),
    ziel: new THREE.Vector3(mitte.x - 4, mitte.y - 2, mitte.z),
    nebel: NEBEL_AKT,
  };
  const posen = STATIONEN.map((_, i) => station(i));
  const pose = (b: Blickpunkt): Pose => (b === "oben" ? oben : b === "akt" ? akt : posen[b]);

  const tourPos = new THREE.Vector3();
  const tourZiel = new THREE.Vector3();
  let tourNebel = NEBEL_TOUR;
  function tour(z: Zustand) {
    const von = pose(z.blick.von);
    const nach = pose(z.blick.nach);
    const s = smooth(z.blick.f);
    tourPos.lerpVectors(von.pos, nach.pos, s);
    tourZiel.lerpVectors(von.ziel, nach.ziel, s);
    tourNebel = THREE.MathUtils.lerp(von.nebel, nach.nebel, s);
    // on the way between two poses the straight line may cut through the slope
    if (tourPos.y < 0) tourPos.y = Math.max(tourPos.y, bodenY(tourPos.x, tourPos.z) + BODEN_FREI);
  }

  // ---- a viewer may drag the view; after FREI_S seconds the tour glides back
  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.enablePan = false;
  controls.minDistance = 6;
  controls.maxDistance = 400;
  const frei = { w: 0 };
  const freiPos = new THREE.Vector3();
  const freiZiel = new THREE.Vector3();
  // only a real drag takes the view; a tap (to pick a shark) leaves the tour running
  let zieht = false;
  controls.addEventListener("start", () => (zieht = true));
  controls.addEventListener("change", () => {
    if (!zieht || frei.w >= 1) return;
    gsap.killTweensOf(frei);
    frei.w = 1;
  });
  controls.addEventListener("end", () => {
    zieht = false;
    if (frei.w > 0) gsap.to(frei, { w: 0, duration: 2.5, delay: FREI_S, ease: "power2.inOut" });
  });

  function kamera(z: Zustand) {
    tour(z);
    if (frei.w >= 1) {
      controls.update();
      freiPos.copy(camera.position);
      freiZiel.copy(controls.target);
    } else {
      camera.position.lerpVectors(tourPos, freiPos, frei.w);
      controls.target.lerpVectors(tourZiel, freiZiel, frei.w);
      camera.lookAt(controls.target);
    }
    NEBEL.uKamTiefe.value = -camera.position.y / Y_PER_M;
    NEBEL.uNebelK.value = tourNebel;
  }

  // ---- what each shark does in this state
  const ansicht = neueAnsicht();
  function setzeAnsicht(z: Zustand, gewaehlt: number | null) {
    const spot = gewaehlt ?? (z.kapitel === 1 ? z.featured : null);
    const tSpot = z.kapitel === 1 && z.featured !== null && gewaehlt === null
      ? z.tKapitel - CH1_INTRO_MS - z.featuredIndex * CH1_STATION_MS
      : performance.now();
    const an = Math.floor(tSpot / SPOT_BLINK_MS) % 2 === 0;
    for (let i = 0; i < ARTEN.length; i++) {
      const tier = STUFE_INDEX[ARTEN[i].tier];
      let glow = 1, scale = 1, flash = 0, sink = 0;
      if (spot !== null) {
        if (i + 1 === spot) {
          flash = an ? 1 : 0;
          scale = 1.6;
        } else {
          glow = 0.6;
        }
      } else if (z.kapitel === 2 && z.akt) {
        const l = z.akt.level[tier] / 255;
        // first the tier blinks, then it fades and sinks
        if (z.akt.phase === 0) flash = tier > 0 ? l : 0;
        glow = 0.2 + 0.8 * l;
        scale = 1.5;
        if (z.akt.phase > 0 && tier > 0) {
          scale = 1.5 * (0.5 + 0.5 * l);
          sink = (1 - l) * 6;
        }
      }
      ansicht.glow[i] = glow;
      ansicht.scale[i] = scale;
      ansicht.flash[i] = flash;
      ansicht.sink[i] = sink;
    }
  }

  // the clear colour matches the fog straight ahead, in case a pixel shows through
  const klar = new THREE.Color();
  function hintergrund() {
    const d = -camera.position.y / Y_PER_M;
    renderer.setClearColor(d > 0 ? wasserFarbe(d, klar) : klar.set("#c6c2b6"), 1);
  }

  let breite = 1;
  let hoehe = 1;
  function resize() {
    breite = window.innerWidth;
    hoehe = window.innerHeight;
    renderer.setSize(breite, hoehe, false);
    camera.aspect = breite / hoehe;
    camera.updateProjectionMatrix();
  }
  resize();

  const proj = new THREE.Vector3();
  function bildschirm(led: number) {
    proj.copy(haie.haiPos[led - 1]).project(camera);
    if (proj.z > 1) return null;
    return { x: ((proj.x + 1) / 2) * breite, y: ((1 - proj.y) / 2) * hoehe };
  }
  return {
    resize,
    bildschirm,
    waehle(x, y) {
      let best: number | null = null;
      let bestD = 48;
      for (const a of ARTEN) {
        const p = bildschirm(a.led);
        if (!p) continue;
        const d = Math.hypot(p.x - x, p.y - y);
        if (d < bestD) {
          bestD = d;
          best = a.led;
        }
      }
      return best;
    },
    render(tSek, z, gewaehlt) {
      kamera(z);
      setzeAnsicht(z, gewaehlt);
      haie.update(tSek, ansicht);
      hintergrund();
      renderer.render(scene, camera);
    },
  };
}
