// The sea surface: one calm plane out to the horizon. From the air it is clear at a steep
// view and reflects the haze at a grazing one; from below it is the bright ceiling of the
// sea. It stays flat and calm, so nothing on screen flickers except the sharks.
import * as THREE from "three";
import { WASSER_GLSL, wasserUniforms } from "./wasser";

/** edge length of the surface in scene units (1 unit = 100 m): far beyond the fog */
const GROESSE = 6000;

const flaecheVertex = /* glsl */ `
  varying vec3 vWorld;
  void main() {
    vec4 w = modelMatrix * vec4(position, 1.0);
    vWorld = w.xyz;
    gl_Position = projectionMatrix * viewMatrix * w;
  }
`;

const flaecheFragment = /* glsl */ `
  ${WASSER_GLSL}
  varying vec3 vWorld;
  void main() {
    vec3 v = normalize(cameraPosition - vWorld);
    vec3 col;
    float a;
    if (cameraPosition.y > 0.0) {
      float fres = pow(1.0 - abs(v.y), 3.0);
      col = mix(uAsagi, uDunst, 0.35 + 0.65 * fres);
      a = 0.35 + 0.6 * fres;
    } else {
      col = mix(uAsagi * 1.2, uHimmel, 0.55);
      a = 0.9;
    }
    gl_FragColor = vec4(nebel(col, vWorld), a);
  }
`;

export function baueMeer(): THREE.Mesh {
  const flaeche = new THREE.Mesh(
    new THREE.PlaneGeometry(GROESSE, GROESSE, 1, 1).rotateX(-Math.PI / 2),
    new THREE.ShaderMaterial({
      vertexShader: flaecheVertex, fragmentShader: flaecheFragment, uniforms: wasserUniforms(),
      transparent: true, depthWrite: false, side: THREE.DoubleSide,
    }),
  );
  flaeche.renderOrder = 2;
  return flaeche;
}

const himmelFragment = /* glsl */ `
  ${WASSER_GLSL}
  varying vec3 vWorld;
  void main() {
    gl_FragColor = vec4(nebelFarbe(normalize(vWorld - cameraPosition)), 1.0);
  }
`;

/** The background: a sphere around the camera in the colour the fog fades to. */
export function baueHintergrund(): THREE.Mesh {
  const kugel = new THREE.Mesh(
    new THREE.SphereGeometry(GROESSE * 0.6, 32, 16),
    new THREE.ShaderMaterial({
      vertexShader: flaecheVertex, fragmentShader: himmelFragment, uniforms: wasserUniforms(),
      side: THREE.BackSide, depthWrite: false, depthTest: false,
    }),
  );
  kugel.renderOrder = -1;
  kugel.frustumCulled = false;
  return kugel;
}
