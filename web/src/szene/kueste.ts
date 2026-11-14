// The real Sagami Bay: land and seabed from the SRTM15+ grid. Past the edges of the grid
// the ground runs on at the height of the edge, far into the fog, so the bay never ends
// on screen.
import * as THREE from "three";
import { GRID, RAND, Y_PER_M, zelle } from "./koordinaten";
import { WASSER_GLSL, wasserUniforms } from "./wasser";

/** extra rows and columns outside the grid, distance from the edge in scene units */
const AUSLAUF = [12, 40, 120, 400, 1500];

const terrainVertex = /* glsl */ `
  varying vec3 vWorld;
  varying vec3 vNormal;
  void main() {
    vec4 w = modelMatrix * vec4(position, 1.0);
    vWorld = w.xyz;
    vNormal = normalize(mat3(modelMatrix) * normal);
    gl_Position = projectionMatrix * viewMatrix * w;
  }
`;

const terrainFragment = /* glsl */ `
  ${WASSER_GLSL}
  varying vec3 vWorld;
  varying vec3 vNormal;

  void main() {
    float hM = vWorld.y / uYPerM;          // height in metres, negative below the sea
    vec3 n = normalize(vNormal);
    float sun = max(dot(n, normalize(vec3(0.45, 1.0, 0.7))), 0.0);
    float shade = 0.42 + 0.68 * sun;
    vec3 col;
    if (hM > 0.0) {
      vec3 sand = vec3(0.86, 0.80, 0.66);
      vec3 gruen = vec3(0.47, 0.56, 0.42);
      vec3 ocker = vec3(0.62, 0.58, 0.48);
      col = mix(sand, gruen, smoothstep(6.0, 22.0, hM));
      col = mix(col, ocker, smoothstep(180.0, 480.0, hM));
      col *= shade;
    } else {
      float d = -hM;
      vec3 sand = vec3(0.86, 0.81, 0.68);
      vec3 schlick = vec3(0.66, 0.64, 0.56);
      vec3 schlamm = vec3(0.50, 0.53, 0.52);
      col = mix(sand, schlick, smoothstep(40.0, 320.0, d));
      col = mix(col, schlamm, smoothstep(320.0, 1200.0, d));
      // the deeper the ground, the more it is lit only by the blue of the water above it;
      // a little lighter than that water, so the slope stays readable as ground
      float licht = 1.0 - exp(-d / 150.0);
      col = mix(col, wasserFarbe(d) * 1.15, licht) * shade;
    }
    gl_FragColor = vec4(nebel(col, vWorld), 1.0);
  }
`;

/** Scene coordinates of the grid columns (west to east) and rows (south to north), with the run-out. */
function achsen() {
  const { nlat, nlon } = GRID;
  const xs: { v: number; j: number }[] = [];
  const zs: { v: number; i: number }[] = [];
  for (const a of [...AUSLAUF].reverse()) xs.push({ v: RAND.x0 - a, j: 0 });
  for (let j = 0; j < nlon; j++) xs.push({ v: RAND.x0 + ((RAND.x1 - RAND.x0) * j) / (nlon - 1), j });
  for (const a of AUSLAUF) xs.push({ v: RAND.x1 + a, j: nlon - 1 });
  for (const a of [...AUSLAUF].reverse()) zs.push({ v: RAND.z1 + a, i: 0 });
  for (let i = 0; i < nlat; i++) zs.push({ v: RAND.z1 + ((RAND.z0 - RAND.z1) * i) / (nlat - 1), i });
  for (const a of AUSLAUF) zs.push({ v: RAND.z0 - a, i: nlat - 1 });
  return { xs, zs };
}

export function baueKueste(): THREE.Mesh {
  const { xs, zs } = achsen();
  const nx = xs.length;
  const nz = zs.length;
  // one vertex per grid cell, rows from south to north; outside the grid the edge height
  const pos = new Float32Array(nx * nz * 3);
  for (let r = 0; r < nz; r++) {
    for (let c = 0; c < nx; c++) {
      const k = (r * nx + c) * 3;
      pos[k] = xs[c].v;
      pos[k + 1] = zelle(zs[r].i, xs[c].j) * Y_PER_M;
      pos[k + 2] = zs[r].v;
    }
  }
  const index: number[] = [];
  for (let r = 0; r < nz - 1; r++) {
    for (let c = 0; c < nx - 1; c++) {
      const a = r * nx + c;
      const b = a + 1;
      const d = a + nx;
      const e = d + 1;
      // counter-clockwise seen from above (+y), with X east and Z south
      index.push(a, b, d, b, e, d);
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geo.setIndex(index);
  geo.computeVertexNormals();
  const terrain = new THREE.Mesh(geo, new THREE.ShaderMaterial({
    vertexShader: terrainVertex, fragmentShader: terrainFragment, uniforms: wasserUniforms(),
  }));
  terrain.frustumCulled = false;
  return terrain;
}
