// One shark silhouette per order, plus the hammerhead for Sphyrnidae.
// Body along +X (tail at -0.5, nose at +0.5), up +Y, sideways Z. Length 1.
import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";

interface Flosse { u: number; h: number; w: number }

interface Form {
  /** radius along the body, tail (u = 0) to nose (u = 1), in steps of 0.1 */
  profil: number[];
  dicke: number;
  /** width / height of the body cross section */
  breit: number;
  rueckenflossen: Flosse[];
  brust: { u: number; spann: number; tief: number; haengen: number };
  schwanz: { oben: number; unten: number; zurueck: number };
  kopf?: "hammer" | "saege";
  laenge: number;
}

export const FORMEN: Record<string, Form> = {
  Carcharhiniformes: {
    profil: [0.05, 0.09, 0.14, 0.2, 0.26, 0.3, 0.31, 0.29, 0.24, 0.16, 0.04],
    dicke: 0.3, breit: 1.0,
    rueckenflossen: [{ u: 0.58, h: 0.14, w: 0.12 }, { u: 0.25, h: 0.04, w: 0.05 }],
    brust: { u: 0.66, spann: 0.17, tief: 0.11, haengen: 0.06 },
    schwanz: { oben: 0.22, unten: 0.1, zurueck: 0.16 },
    laenge: 1.0,
  },
  Lamniformes: {
    profil: [0.05, 0.08, 0.15, 0.24, 0.31, 0.35, 0.36, 0.33, 0.27, 0.17, 0.04],
    dicke: 0.3, breit: 1.0,
    rueckenflossen: [{ u: 0.6, h: 0.15, w: 0.13 }],
    brust: { u: 0.67, spann: 0.2, tief: 0.11, haengen: 0.05 },
    schwanz: { oben: 0.26, unten: 0.22, zurueck: 0.13 },
    laenge: 1.15,
  },
  Squaliformes: {
    profil: [0.04, 0.07, 0.11, 0.16, 0.2, 0.23, 0.24, 0.23, 0.2, 0.14, 0.04],
    dicke: 0.3, breit: 1.05,
    rueckenflossen: [{ u: 0.62, h: 0.08, w: 0.08 }, { u: 0.33, h: 0.07, w: 0.07 }],
    brust: { u: 0.7, spann: 0.12, tief: 0.08, haengen: 0.05 },
    schwanz: { oben: 0.16, unten: 0.07, zurueck: 0.14 },
    laenge: 0.85,
  },
  Hexanchiformes: {
    profil: [0.04, 0.06, 0.08, 0.1, 0.12, 0.13, 0.13, 0.13, 0.12, 0.1, 0.05],
    dicke: 0.3, breit: 1.0,
    rueckenflossen: [{ u: 0.22, h: 0.05, w: 0.08 }],
    brust: { u: 0.76, spann: 0.08, tief: 0.06, haengen: 0.04 },
    schwanz: { oben: 0.05, unten: 0.08, zurueck: 0.22 },
    laenge: 1.25,
  },
  Heterodontiformes: {
    profil: [0.05, 0.08, 0.12, 0.18, 0.24, 0.28, 0.31, 0.33, 0.33, 0.3, 0.18],
    dicke: 0.3, breit: 0.9,
    rueckenflossen: [{ u: 0.66, h: 0.13, w: 0.09 }, { u: 0.36, h: 0.11, w: 0.08 }],
    brust: { u: 0.68, spann: 0.15, tief: 0.12, haengen: 0.07 },
    schwanz: { oben: 0.14, unten: 0.07, zurueck: 0.12 },
    laenge: 0.8,
  },
  Orectolobiformes: {
    profil: [0.05, 0.09, 0.15, 0.22, 0.29, 0.33, 0.35, 0.36, 0.35, 0.32, 0.22],
    dicke: 0.3, breit: 1.35,
    rueckenflossen: [{ u: 0.52, h: 0.13, w: 0.12 }, { u: 0.3, h: 0.05, w: 0.06 }],
    brust: { u: 0.68, spann: 0.2, tief: 0.13, haengen: 0.06 },
    schwanz: { oben: 0.24, unten: 0.1, zurueck: 0.16 },
    laenge: 1.3,
  },
  Squatiniformes: {
    profil: [0.03, 0.05, 0.07, 0.1, 0.15, 0.2, 0.24, 0.26, 0.25, 0.21, 0.12],
    dicke: 0.3, breit: 2.4,
    rueckenflossen: [{ u: 0.26, h: 0.05, w: 0.05 }, { u: 0.16, h: 0.04, w: 0.04 }],
    brust: { u: 0.62, spann: 0.3, tief: 0.26, haengen: 0.0 },
    schwanz: { oben: 0.08, unten: 0.06, zurueck: 0.08 },
    laenge: 0.95,
  },
  Pristiophoriformes: {
    profil: [0.04, 0.07, 0.11, 0.16, 0.2, 0.22, 0.23, 0.22, 0.19, 0.13, 0.04],
    dicke: 0.3, breit: 1.3,
    rueckenflossen: [{ u: 0.58, h: 0.08, w: 0.08 }, { u: 0.33, h: 0.07, w: 0.07 }],
    brust: { u: 0.68, spann: 0.14, tief: 0.09, haengen: 0.03 },
    schwanz: { oben: 0.13, unten: 0.05, zurueck: 0.12 },
    kopf: "saege",
    laenge: 0.9,
  },
};

FORMEN.Sphyrnidae = { ...FORMEN.Carcharhiniformes, kopf: "hammer", laenge: 1.1 };

/** Which silhouette a species gets: family Sphyrnidae first, then its order. */
export function formName(order: string, family: string): string {
  if (family === "Sphyrnidae") return "Sphyrnidae";
  if (!(order in FORMEN)) throw new Error(`no shark shape for order ${order}`);
  return order;
}

const RING = 14;
const STEPS = 28;

/**
 * A smooth body (shared vertices, so the normals round off) plus flat fins: a pointed
 * snout, swept dorsal fins, pectoral fins and the asymmetric tail of a shark.
 */
export function formGeometrie(f: Form): THREE.BufferGeometry {
  const radius = (u: number) => {
    const k = Math.min(f.profil.length - 1.0001, Math.max(0, u * 10));
    const i = Math.floor(k);
    return (f.profil[i] * (1 - (k - i)) + f.profil[i + 1] * (k - i)) * f.dicke;
  };
  const ringPunkt = (u: number, j: number): [number, number, number] => {
    const a = (j / RING) * Math.PI * 2;
    const r = radius(u);
    // a flatter belly: the lower half is squeezed
    const y = Math.sin(a) * r * (Math.sin(a) < 0 ? 0.72 : 1);
    return [u - 0.5, y, Math.cos(a) * r * f.breit];
  };

  // body: rings from tail (u = 0) to nose (u = 1), closed with one point at each end
  const pos: number[] = [];
  for (let k = 0; k <= STEPS; k++) {
    for (let j = 0; j < RING; j++) pos.push(...ringPunkt(k / STEPS, j));
  }
  const heck = pos.length / 3;
  pos.push(-0.5, 0, 0);
  const nase = pos.length / 3;
  // the snout comes to a point a little below the body axis
  pos.push(0.56, -0.012, 0);
  const idx: number[] = [];
  for (let k = 0; k < STEPS; k++) {
    for (let j = 0; j < RING; j++) {
      const a = k * RING + j;
      const b = k * RING + ((j + 1) % RING);
      const c = a + RING;
      const d = b + RING;
      idx.push(a, c, b, b, c, d);
    }
  }
  for (let j = 0; j < RING; j++) {
    const jn = (j + 1) % RING;
    idx.push(heck, j, jn);
    idx.push(STEPS * RING + j, nase, STEPS * RING + jn);
  }
  const body = new THREE.BufferGeometry();
  body.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  body.setIndex(idx);
  body.computeVertexNormals();

  // fins: flat, drawn from both sides
  const tri: number[] = [];
  const t = (...p: number[][]) => { for (const q of p) tri.push(q[0], q[1], q[2]); };
  for (const fl of f.rueckenflossen) {
    const top = radius(fl.u) * 0.9;
    const x = fl.u - 0.5;
    const front = [x + fl.w / 2, top, 0];
    const back = [x - fl.w / 2, top, 0];
    const apex = [x - fl.w * 0.45, top + fl.h, 0];
    const notch = [x - fl.w * 0.35, top + fl.h * 0.25, 0];
    t(front, back, notch);
    t(front, notch, apex);
  }

  const br = f.brust;
  const bx = br.u - 0.5;
  const bz = radius(br.u) * f.breit * 0.8;
  const by = -radius(br.u) * 0.45;
  for (const s of [1, -1]) {
    const rootF = [bx + br.tief / 2, by, s * bz];
    const rootB = [bx - br.tief / 2, by, s * bz];
    const tip = [bx - br.tief * 0.95, by - br.haengen, s * (bz + br.spann)];
    const tipF = [bx - br.tief * 0.35, by - br.haengen * 0.7, s * (bz + br.spann * 0.8)];
    t(rootF, rootB, tip);
    t(rootF, tip, tipF);
  }

  // tail: the long upper lobe swept back, a shorter lower lobe, a notch between them
  const sw = f.schwanz;
  const root = [-0.47, 0.01, 0];
  const rootLow = [-0.47, -0.01, 0];
  const end = [-0.53, 0, 0];
  const oben = [-0.5 - sw.zurueck, sw.oben, 0];
  const obenMitte = [-0.5 - sw.zurueck * 0.75, sw.oben * 0.55, 0];
  const unten = [-0.5 - sw.zurueck * 0.55, -sw.unten, 0];
  t(root, end, obenMitte);
  t(root, obenMitte, oben);
  t(rootLow, end, unten);

  if (f.kopf === "hammer") {
    const hx = 0.43, half = 0.15, chord = 0.05, y = 0.005;
    t([hx + chord, y, -half], [hx, y, -half], [hx + chord, y, half]);
    t([hx, y, -half], [hx, y, half], [hx + chord, y, half]);
  }
  if (f.kopf === "saege") {
    const len = 0.32, w = 0.018;
    t([0.5, 0, -w], [0.5 + len, 0, 0], [0.5, 0, w]);
    for (let i = 1; i < 8; i++) {
      const x = 0.5 + (i / 8) * len;
      const ww = w * (1 - i / 8);
      for (const s of [1, -1]) t([x, 0, s * ww], [x + 0.012, 0, s * ww], [x + 0.004, 0, s * (ww + 0.02)]);
    }
  }
  const fins = new THREE.BufferGeometry();
  fins.setAttribute("position", new THREE.Float32BufferAttribute(tri, 3));
  fins.computeVertexNormals();

  const geo = mergeGeometries([body.toNonIndexed(), fins]);
  if (!geo) throw new Error("shark geometry could not be merged");
  geo.scale(f.laenge, f.laenge, f.laenge);
  return geo;
}
