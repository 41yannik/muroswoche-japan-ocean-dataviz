// 109 sharks, one per LED, each swimming a small loop above its real place in Sagami Bay
// (kueste.json). One InstancedMesh per silhouette. The sharks themselves carry the Red List
// colour and the blink of the model: a blinking shark turns fully into its colour and back,
// with nothing drawn around it.
import * as THREE from "three";
import arten from "../data/arten.json";
import { bodenY, LED_ORTE, szenePunkt, Y_PER_M } from "./koordinaten";
import { formGeometrie, formName, FORMEN } from "./formen";
import { WASSER_GLSL, wasserUniforms } from "./wasser";

export const STUFE_INDEX: Record<string, number> = { LC: 0, VU: 1, EN: 2, CR: 3 };
export const STUFE_FARBE = ["#3a7bff", "#ffc000", "#ff5000", "#ff2a2a"];

export interface Art {
  led: number;
  species: string;
  name_en: string;
  name_ja: string;
  order: string;
  family: string;
  tier: string;
  depth_m: number;
}

export const ARTEN = arten as Art[];

const sharkVertex = /* glsl */ `
  uniform float uTime;
  attribute float aPhase;
  attribute float aGlow;
  attribute float aFlash;
  varying vec3 vNormal;
  varying vec3 vView;
  varying vec3 vWorld;
  varying vec3 vColor;
  varying float vGlow;
  varying float vFlash;
  void main() {
    vec3 p = position;
    // the tail beats, the head stays almost still
    float u = clamp(p.x + 0.5, 0.0, 1.0);
    p.z += sin(uTime * 3.2 + aPhase * 6.2832 - u * 5.0) * 0.07 * pow(1.0 - u, 1.6);
    vec4 w = modelMatrix * instanceMatrix * vec4(p, 1.0);
    vNormal = normalize(mat3(modelMatrix) * mat3(instanceMatrix) * normal);
    vView = normalize(cameraPosition - w.xyz);
    vWorld = w.xyz;
    vColor = instanceColor;
    vGlow = aGlow;
    vFlash = aFlash;
    gl_Position = projectionMatrix * viewMatrix * w;
  }
`;

const sharkFragment = /* glsl */ `
  ${WASSER_GLSL}
  varying vec3 vNormal;
  varying vec3 vView;
  varying vec3 vWorld;
  varying vec3 vColor;
  varying float vGlow;
  varying float vFlash;
  void main() {
    vec3 n = normalize(vNormal);
    if (!gl_FrontFacing) n = -n;
    // countershading: a back tinted with the Red List colour, a light belly
    vec3 ruecken = mix(vec3(0.30, 0.40, 0.48), vColor, 0.5);
    vec3 bauch = vec3(0.90, 0.90, 0.86);
    vec3 col = mix(bauch, ruecken, smoothstep(-0.35, 0.25, n.y));
    col *= 0.6 + 0.45 * max(dot(n, normalize(vec3(0.3, 1.0, 0.5))), 0.0);
    // a faint edge in the tier colour keeps the outline readable against the water
    float rim = pow(1.0 - abs(dot(n, vView)), 2.0);
    col += vColor * rim * 0.35;
    // the blink: the whole body turns into its tier colour, lit like the rest of the shark
    float licht = 0.8 + 0.3 * max(dot(n, normalize(vec3(0.3, 1.0, 0.5))), 0.0);
    col = mix(col, vColor * licht, vFlash);
    // sharks that step back lose colour and sink into the water
    float g = dot(col, vec3(0.299, 0.587, 0.114));
    col = mix(vec3(g), col, 0.3 + 0.7 * vGlow);
    col = imWasser(col, vWorld, 1.0 - 0.5 * vFlash);
    col = mix(nebelFarbe(normalize(vWorld - cameraPosition)), col, 0.35 + 0.65 * vGlow);
    gl_FragColor = vec4(col, 1.0);
  }
`;

export interface HaiAnsicht {
  /** per species (index = led - 1): presence 0..1, scale factor, flash 0..1, sink in units */
  glow: Float32Array;
  scale: Float32Array;
  flash: Float32Array;
  sink: Float32Array;
}

export interface Haie {
  group: THREE.Group;
  /** centre of each shark's loop, index = led - 1 */
  ankerPos: THREE.Vector3[];
  /** current position of each shark */
  haiPos: THREE.Vector3[];
  update(t: number, a: HaiAnsicht): void;
}

export function neueAnsicht(): HaiAnsicht {
  const n = ARTEN.length;
  return {
    glow: new Float32Array(n).fill(1),
    scale: new Float32Array(n).fill(1),
    flash: new Float32Array(n),
    sink: new Float32Array(n),
  };
}

/** length of a shark in scene units (1 unit = 100 m): drawn for the eye, not to scale */
export const SHARK_LEN = 3;
/** a shallow species still swims below the surface */
const MIN_TIEFE = 0.8;
/** free water between the loop and the seabed */
const ABSTAND = 0.9;

function zufall(led: number): number {
  const h = Math.sin(led * 12.9898) * 43758.5453;
  return h - Math.floor(h);
}

/**
 * Centre of the loop: the real place and depth of the species. Where the seabed there is
 * higher than the loop, the loop moves seawards (south, +z) at the same depth until it is
 * clear of the ground. The depth is the fact; the position along the slope gives way.
 */
export function anker(led: number, radius: number): THREE.Vector3 {
  const ort = LED_ORTE[led - 1];
  const p = szenePunkt(ort.lat, ort.lon, 0);
  p.y = -Math.max(ort.depth_m * Y_PER_M, MIN_TIEFE);
  const frei = () => {
    for (let k = 0; k < 8; k++) {
      const a = (k / 8) * Math.PI * 2;
      if (bodenY(p.x + Math.cos(a) * radius, p.z + Math.sin(a) * radius) > p.y - ABSTAND) return false;
    }
    return bodenY(p.x, p.z) <= p.y - ABSTAND;
  };
  for (let s = 0; s < 120 && !frei(); s++) p.z += 0.25;
  return p;
}

/** the ellipse of a highlighted shark: half axes across and along the view, angular speed (rad/s) */
const QUER_X = 1.5;
const QUER_Z = 0.2;
const QUER_W = 0.3;

export function baueHaie(): Haie {
  const group = new THREE.Group();
  const timeU = { value: 0 };

  const swim = ARTEN.map((a, i) => {
    const r = zufall(a.led);
    return {
      radius: 2.6 + r * 1.4,
      speed: (0.35 + r * 0.2) * (i % 2 ? 1 : -1),
      phase: r * Math.PI * 2,
    };
  });
  const ankerPos = ARTEN.map((a, i) => anker(a.led, swim[i].radius));
  const haiPos = ankerPos.map((p) => p.clone());

  const gruppen = new Map<string, number[]>();
  ARTEN.forEach((a, i) => {
    const name = formName(a.order, a.family);
    if (!gruppen.has(name)) gruppen.set(name, []);
    gruppen.get(name)!.push(i);
  });
  const material = new THREE.ShaderMaterial({
    vertexShader: sharkVertex, fragmentShader: sharkFragment, side: THREE.DoubleSide,
    uniforms: { ...wasserUniforms(), uTime: timeU },
  });
  const meshes: { mesh: THREE.InstancedMesh; idx: number[]; glow: THREE.InstancedBufferAttribute; flash: THREE.InstancedBufferAttribute }[] = [];
  const color = new THREE.Color();
  for (const [name, idx] of gruppen) {
    const geo = formGeometrie(FORMEN[name]);
    geo.setAttribute("aPhase", new THREE.InstancedBufferAttribute(new Float32Array(idx.map((i) => swim[i].phase / (Math.PI * 2))), 1));
    const glow = new THREE.InstancedBufferAttribute(new Float32Array(idx.length).fill(1), 1);
    const flash = new THREE.InstancedBufferAttribute(new Float32Array(idx.length), 1);
    glow.setUsage(THREE.DynamicDrawUsage);
    flash.setUsage(THREE.DynamicDrawUsage);
    geo.setAttribute("aGlow", glow);
    geo.setAttribute("aFlash", flash);
    const mesh = new THREE.InstancedMesh(geo, material, idx.length);
    mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    idx.forEach((i, k) => mesh.setColorAt(k, color.set(STUFE_FARBE[STUFE_INDEX[ARTEN[i].tier]])));
    mesh.frustumCulled = false;
    meshes.push({ mesh, idx, glow, flash });
    group.add(mesh);
  }

  const dummy = new THREE.Object3D();
  const shown = new Float32Array(ARTEN.length).fill(1);
  const sunk = new Float32Array(ARTEN.length);

  return {
    group, ankerPos, haiPos,
    update(t, a) {
      timeU.value = t;
      for (let i = 0; i < ARTEN.length; i++) {
        shown[i] += (a.scale[i] - shown[i]) * 0.12;
        sunk[i] += (a.sink[i] - sunk[i]) * 0.08;
      }
      for (const { mesh, idx, glow, flash } of meshes) {
        idx.forEach((i, k) => {
          const s = swim[i];
          const ang = s.phase + (t * s.speed * 3) / s.radius;
          const c = ankerPos[i];
          const dir = Math.sign(s.speed);
          // a highlighted shark leaves its circle for a long flat ellipse across the view
          // (the camera looks north, along -z), so it is seen from the side, not head-on
          const w = THREE.MathUtils.clamp((shown[i] - 1) / 0.5, 0, 1);
          const e = s.phase + t * QUER_W * dir;
          const ex = s.radius * QUER_X;
          const ez = s.radius * QUER_Z;
          const kx = THREE.MathUtils.lerp(Math.cos(ang) * s.radius, Math.cos(e) * ex, w);
          const kz = THREE.MathUtils.lerp(Math.sin(ang) * s.radius, Math.sin(e) * ez, w);
          const tx = THREE.MathUtils.lerp(-Math.sin(ang) * s.radius, -Math.sin(e) * ex, w) * dir;
          const tz = THREE.MathUtils.lerp(Math.cos(ang) * s.radius, Math.cos(e) * ez, w) * dir;
          const p = haiPos[i].set(c.x + kx, c.y + Math.sin(t * 0.7 + s.phase) * 0.25 - sunk[i], c.z + kz);
          dummy.position.copy(p);
          // the shark's nose is its local +x; turn it along the direction of travel
          dummy.rotation.set(0, Math.atan2(-tz, tx), 0);
          dummy.scale.setScalar(SHARK_LEN * Math.max(shown[i], 0.0001));
          dummy.updateMatrix();
          mesh.setMatrixAt(k, dummy.matrix);
          glow.setX(k, a.glow[i]);
          flash.setX(k, a.flash[i]);
        });
        mesh.instanceMatrix.needsUpdate = true;
        glow.needsUpdate = true;
        flash.needsUpdate = true;
      }
    },
  };
}
