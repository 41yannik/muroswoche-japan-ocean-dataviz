// Colours of the bay and the one water model every shader shares. The water colour follows
// the traditional Japanese blues from the surface down (asagi, hanada, ai, kon) and changes
// where the light really goes: little is left at 200 m, none at 1,000 m (JAMSTEC GODAC).
// Everything fades into fog of the water colour around the camera, so the world has no edge.
import * as THREE from "three";
import { Y_PER_M } from "./koordinaten";

// Every shader here works in plain sRGB values, as written in the palette and the GLSL
// literals, and writes them out unchanged. With colour management on, three.js would turn
// "#ffc000" into linear (1, 0.53, 0) and the yellow of the Red List would show as orange.
// This runs before the first THREE.Color of the scene is made (all modules import this one).
THREE.ColorManagement.enabled = false;

export const FARBE = {
  /** shironeri 白練, lightened: the sky and the text on dark water */
  himmel: new THREE.Color("#f3efe8"),
  /** kamenozoki 瓶覗: haze at the horizon */
  dunst: new THREE.Color("#c6c2b6"),
  /** asagi 浅葱: water 0 to 100 m */
  asagi: new THREE.Color("#48929b"),
  /** hanada 縹: water at about 300 m */
  hanada: new THREE.Color("#044f67"),
  /** ai 藍: water at about 700 m */
  ai: new THREE.Color("#264348"),
  /** kon 紺: water below 1,000 m, never black */
  kon: new THREE.Color("#192236"),
  /** sumi 墨: text on light ground */
  sumi: new THREE.Color("#27221f"),
};

/** depth (m) at which each colour of the ramp is reached; little light is left at 200 m, so the water is close to hanada there */
const RAMPE: [number, THREE.Color][] = [
  [100, FARBE.asagi],
  [300, FARBE.hanada],
  [700, FARBE.ai],
  [1000, FARBE.kon],
];

/** water tint per scene unit of ray length, for points under water seen from the air */
export const WASSER_K = 0.03;

/** Fog shared by every material; szene.ts sets the values each frame. */
export const NEBEL = {
  /** depth of the camera in metres, negative above the sea */
  uKamTiefe: { value: 0 },
  /** fog density under water, per scene unit */
  uNebelK: { value: 0.018 },
  /** haze density in the air, per scene unit */
  uLuftK: { value: 0.0035 },
};

export function wasserUniforms() {
  return {
    uAsagi: { value: FARBE.asagi },
    uHanada: { value: FARBE.hanada },
    uAi: { value: FARBE.ai },
    uKon: { value: FARBE.kon },
    uHimmel: { value: FARBE.himmel },
    uDunst: { value: FARBE.dunst },
    uYPerM: { value: Y_PER_M },
    uWasserK: { value: WASSER_K },
    ...NEBEL,
  };
}

/** The same ramp as wasserFarbe() in GLSL. */
export function wasserFarbe(depthM: number, out = new THREE.Color()): THREE.Color {
  out.copy(RAMPE[0][1]);
  for (let k = 1; k < RAMPE.length; k++) {
    const [d0] = RAMPE[k - 1];
    const [d1, c] = RAMPE[k];
    out.lerp(c, THREE.MathUtils.smoothstep(depthM, d0, d1));
  }
  return out;
}

export const WASSER_GLSL = /* glsl */ `
  uniform vec3 uAsagi;
  uniform vec3 uHanada;
  uniform vec3 uAi;
  uniform vec3 uKon;
  uniform vec3 uHimmel;
  uniform vec3 uDunst;
  uniform float uYPerM;
  uniform float uWasserK;
  uniform float uKamTiefe;
  uniform float uNebelK;
  uniform float uLuftK;

  vec3 wasserFarbe(float depthM) {
    vec3 c = mix(uAsagi, uHanada, smoothstep(${RAMPE[0][0]}.0, ${RAMPE[1][0]}.0, depthM));
    c = mix(c, uAi, smoothstep(${RAMPE[1][0]}.0, ${RAMPE[2][0]}.0, depthM));
    return mix(c, uKon, smoothstep(${RAMPE[2][0]}.0, ${RAMPE[3][0]}.0, depthM));
  }

  // what lies far away in direction dir: under water the water a little above or below the
  // camera (lighter towards the surface), in the air the haze at the horizon and the sky above
  vec3 nebelFarbe(vec3 dir) {
    if (uKamTiefe > 0.0) return wasserFarbe(clamp(uKamTiefe - dir.y * 200.0, 0.0, 1400.0));
    return mix(uDunst, uHimmel, smoothstep(0.0, 0.3, dir.y));
  }

  // length of the segment camera -> p that lies below the surface (y = 0)
  float wasserWeg(vec3 cam, vec3 p) {
    if (p.y >= 0.0) return 0.0;
    float len = length(cam - p);
    if (cam.y <= 0.0) return len;
    return len * (-p.y) / (cam.y - p.y);
  }

  vec3 nebel(vec3 col, vec3 p) {
    vec3 d = p - cameraPosition;
    float dist = length(d);
    vec3 dir = d / max(dist, 1e-4);
    if (uKamTiefe > 0.0) {
      float f = 1.0 - exp(-pow(dist * uNebelK, 2.0));
      return mix(col, nebelFarbe(dir), f);
    }
    // from the air: tinted by the water the ray crosses, then haze towards the horizon
    float w = 1.0 - exp(-wasserWeg(cameraPosition, p) * uWasserK);
    col = mix(col, wasserFarbe(max(-p.y, 0.0) / uYPerM), w);
    float f = 1.0 - exp(-pow(dist * uLuftK, 2.0));
    return mix(col, nebelFarbe(dir), f);
  }

  vec3 imWasser(vec3 col, vec3 p, float staerke) {
    return mix(col, nebel(col, p), staerke);
  }
`;
