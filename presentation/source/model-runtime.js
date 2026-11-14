import * as THREE from '../../web/node_modules/three/build/three.module.js';
import hang from '../../web/src/data/hang.json';
import { FORMEN, formGeometrie, formName } from '../../web/src/szene/formen.ts';

const source = window.SAGAMI_GEOMETRY;
const records = window.SHARK_DATA || [];
const views = [];
const ledState = [];
const recordById = new Map(records.map(record => [record.led, record]));
const tiers = new Map(records.map(record => [record.led, record.tier]));
const colors = { LC: 0x58b8df, VU: 0xf0cd55, EN: 0xf18c45, CR: 0xe65b55 };
const ranks = { LC: 0, VU: 0, EN: 0, CR: 0 };
let litCount = 109;

function glowTexture() {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 64;
  const context = canvas.getContext('2d');
  const gradient = context.createRadialGradient(32, 32, 1, 32, 32, 31);
  gradient.addColorStop(0, 'rgba(255,255,255,1)');
  gradient.addColorStop(0.18, 'rgba(255,255,255,.9)');
  gradient.addColorStop(0.48, 'rgba(255,255,255,.26)');
  gradient.addColorStop(1, 'rgba(255,255,255,0)');
  context.fillStyle = gradient;
  context.fillRect(0, 0, 64, 64);
  return new THREE.CanvasTexture(canvas);
}
const glowMap = glowTexture();

function geometryFor(part) {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(part.positions, 3));
  geometry.setIndex(part.indices);
  geometry.computeVertexNormals();
  return geometry;
}

const partAssets = source.parts.map(part => {
  const color = part.kind === 'wood'
    ? new THREE.Color(...part.color)
    : new THREE.Color(part.kind === 'carrier' ? 0x263b42 : 0x172c34);
  const material = new THREE.MeshStandardMaterial({
    color,
    roughness: part.kind === 'wood' ? 0.72 : 0.48,
    metalness: part.kind === 'wood' ? 0.04 : 0.28,
    side: THREE.DoubleSide,
  });
  return { geometry: geometryFor(part), material };
});

// Slide 1: physical laser-cut wooden model of Sagami Bay
function createBoardView(host) {
  const canvas = host.querySelector('canvas');
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: 'high-performance' });
    renderer.setClearColor(0x000000, 0);
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 0.82;
  } catch (error) {
    host.classList.add('fallback');
    return;
  }
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 3000);
  const root = new THREE.Group();
  const content = new THREE.Group();
  scene.add(root);
  root.add(content);
  partAssets.forEach(asset => content.add(new THREE.Mesh(asset.geometry, asset.material)));
  const box = new THREE.Box3().setFromObject(content);
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const radius = size.length() * 0.5;
  content.position.copy(center).multiplyScalar(-1);
  root.rotation.y = -0.18;
  const ledGeometry = new THREE.BoxGeometry(2.6, 2.6, 2.6);
  source.leds.forEach(led => {
    const tier = tiers.get(led.id) || 'LC';
    const material = new THREE.MeshBasicMaterial({ color: colors[tier], toneMapped: false });
    const glowMaterial = new THREE.SpriteMaterial({
      map: glowMap,
      color: colors[tier],
      transparent: true,
      opacity: 0.9,
      depthWrite: false,
      depthTest: false,
      blending: THREE.AdditiveBlending,
      toneMapped: false,
    });
    const mesh = new THREE.Mesh(ledGeometry, material);
    const glow = new THREE.Sprite(glowMaterial);
    mesh.position.fromArray(led.position);
    mesh.scale.setScalar(1.6);
    glow.position.copy(mesh.position);
    glow.scale.set(11, 11, 1);
    content.add(mesh, glow);
  });
  const cameraDirection = new THREE.Vector3(0.9, 0.68, 1.48).normalize();
  camera.near = radius / 100;
  camera.far = radius * 10;
  scene.add(new THREE.HemisphereLight(0xbdeeff, 0x17343b, 1.35));
  const key = new THREE.DirectionalLight(0xffead0, 2);
  key.position.set(radius, radius * 1.4, radius);
  scene.add(key);
  const rim = new THREE.DirectionalLight(0x63cde1, 1.5);
  rim.position.set(-radius, 0.3 * radius, -radius);
  scene.add(rim);
  let dragging = false, x = 0, y = 0, yaw = -0.18, pitch = 0;
  canvas.addEventListener('pointerdown', event => {
    dragging = true;
    x = event.clientX;
    y = event.clientY;
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener('pointermove', event => {
    if (!dragging) return;
    yaw = Math.max(-0.9, Math.min(0.55, yaw + (event.clientX - x) * 0.006));
    pitch = Math.max(-0.2, Math.min(0.26, pitch + (event.clientY - y) * 0.004));
    x = event.clientX;
    y = event.clientY;
    root.rotation.set(pitch, yaw, 0);
  });
  canvas.addEventListener('pointerup', () => (dragging = false));
  canvas.addEventListener('pointercancel', () => (dragging = false));
  const resize = () => {
    const rect = host.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    renderer.setPixelRatio(Math.min(devicePixelRatio, 1.7));
    renderer.setSize(rect.width, rect.height, false);
    camera.aspect = rect.width / rect.height;
    const vertical = THREE.MathUtils.degToRad(camera.fov);
    const horizontal = 2 * Math.atan(Math.tan(vertical / 2) * camera.aspect);
    const distance = (radius / Math.sin(Math.min(vertical, horizontal) / 2)) * 1.04;
    camera.position.copy(cameraDirection).multiplyScalar(distance);
    camera.lookAt(0, 0, 0);
    camera.updateProjectionMatrix();
  };
  new ResizeObserver(resize).observe(host);
  resize();
  host.classList.add('ready');
  views.push({ host, renderer, scene, camera, update: null });
}

// Slide 4: real Sagami Bay sea with 109 swimming 3D sharks
const seabedVertex = /* glsl */ `
  varying vec3 vPos;
  varying vec3 vNormal;
  void main() {
    vPos = position;
    vNormal = normalize(normal);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

const seabedFragment = /* glsl */ `
  uniform float uTime;
  varying vec3 vPos;
  varying vec3 vNormal;
  void main() {
    // vPos.y runs from ~5 (1305 m deep) to ~270 (0 m surface)
    float depthNorm = clamp((265.0 - vPos.y) / 260.0, 0.0, 1.0);
    vec3 n = normalize(vNormal);
    float sun = max(dot(n, normalize(vec3(0.35, 0.9, 0.45))), 0.0);

    vec3 shallowSand = vec3(0.36, 0.64, 0.66);
    vec3 shelfRock = vec3(0.14, 0.37, 0.46);
    vec3 bathyalSlope = vec3(0.06, 0.19, 0.28);
    vec3 abyssFloor = vec3(0.03, 0.09, 0.16);

    vec3 col = mix(shallowSand, shelfRock, smoothstep(0.0, 0.24, depthNorm));
    col = mix(col, bathyalSlope, smoothstep(0.22, 0.62, depthNorm));
    col = mix(col, abyssFloor, smoothstep(0.58, 1.0, depthNorm));

    // Gentle sunlit caustics on the shallow seabed (0 - 300 m)
    float c1 = sin(vPos.x * 0.13 + uTime * 1.4 + sin(vPos.z * 0.11 - uTime * 0.9));
    float c2 = cos(vPos.z * 0.15 - uTime * 1.1 + cos(vPos.x * 0.09 + uTime * 0.8));
    float caustic = pow(clamp((c1 * c2) * 0.5 + 0.5, 0.0, 1.0), 3.0);
    float shallowMask = (1.0 - smoothstep(0.05, 0.38, depthNorm)) * max(n.y, 0.0);
    col += vec3(0.24, 0.58, 0.66) * caustic * shallowMask * 0.55;

    // Subtle bathymetric contour lines (200 m, 500 m, 1000 m)
    float depthM = max(0.0, (263.52 - vPos.y) / 0.20108);
    float grid100 = abs(fract(depthM / 100.0 - 0.5) - 0.5) / fwidth(depthM / 100.0 + 1e-4);
    float line = 1.0 - smoothstep(0.0, 1.6, grid100);
    col += vec3(0.32, 0.72, 0.80) * line * 0.16 * (1.0 - depthNorm * 0.55);

    col *= 0.58 + 0.52 * sun;
    gl_FragColor = vec4(col, 1.0);
  }
`;

const surfaceVertex = /* glsl */ `
  uniform float uTime;
  varying vec3 vPos;
  varying float vWave;
  void main() {
    vec3 p = position;
    float w = sin(p.x * 0.055 + uTime * 1.35) * cos(p.z * 0.048 + uTime * 1.05) * 2.2
            + sin((p.x + p.z) * 0.09 - uTime * 1.8) * 0.9;
    p.y += w;
    vPos = p;
    vWave = w;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
  }
`;

const surfaceFragment = /* glsl */ `
  varying vec3 vPos;
  varying float vWave;
  void main() {
    float crest = smoothstep(-1.5, 2.4, vWave);
    vec3 deepWater = vec3(0.18, 0.58, 0.68);
    vec3 skyShimmer = vec3(0.68, 0.95, 0.98);
    vec3 col = mix(deepWater, skyShimmer, crest * 0.72);
    float edgeFade = smoothstep(0.0, 18.0, vPos.x) * smoothstep(298.4, 280.0, vPos.x)
                   * smoothstep(-280.0, -258.0, vPos.z) * smoothstep(0.0, -18.0, vPos.z);
    gl_FragColor = vec4(col, (0.34 + crest * 0.26) * (0.45 + 0.55 * edgeFade));
  }
`;

const sharkVertex = /* glsl */ `
  uniform float uTime;
  attribute float aPhase;
  attribute float aGlow;
  attribute float aFlash;
  varying vec3 vNormal;
  varying vec3 vView;
  varying vec3 vColor;
  varying float vGlow;
  varying float vFlash;
  varying float vBodyU;
  void main() {
    vec3 p = position;
    // Nose is at +0.5, tail at -0.5: tail beats smoothly while swimming
    float u = clamp(p.x + 0.5, 0.0, 1.0);
    float swimSpeed = mix(1.2, 4.2, clamp(aGlow, 0.0, 1.0));
    p.z += sin(uTime * swimSpeed + aPhase * 6.28318 - u * 5.2) * 0.085 * pow(1.0 - u, 1.5);
    vec4 w = modelMatrix * instanceMatrix * vec4(p, 1.0);
    vNormal = normalize(mat3(modelMatrix) * mat3(instanceMatrix) * normal);
    vView = normalize(cameraPosition - w.xyz);
    vColor = instanceColor;
    vGlow = aGlow;
    vFlash = aFlash;
    vBodyU = u;
    gl_Position = projectionMatrix * viewMatrix * w;
  }
`;

const sharkFragment = /* glsl */ `
  varying vec3 vNormal;
  varying vec3 vView;
  varying vec3 vColor;
  varying float vGlow;
  varying float vFlash;
  varying float vBodyU;
  void main() {
    vec3 n = normalize(vNormal);
    if (!gl_FrontFacing) n = -n;
    float sun = max(dot(n, normalize(vec3(0.35, 1.0, 0.55))), 0.0);
    float rim = pow(1.0 - abs(dot(n, vView)), 1.85);

    // Realistic countershading: dorsal back richly tinted with Red List colour, pale silver belly
    vec3 dorsal = mix(vec3(0.14, 0.28, 0.36), vColor, 0.78);
    vec3 belly = mix(vec3(0.84, 0.92, 0.94), vColor, 0.22);
    vec3 col = mix(belly, dorsal, smoothstep(-0.35, 0.22, n.y));
    col *= 0.58 + 0.52 * sun;
    col += vColor * rim * (0.65 + 0.55 * vGlow);

    // Blink highlight turns the whole shark body into a bright bioluminescent silhouette
    col = mix(col, vColor * (1.15 + 0.35 * sun), vFlash * 0.85);

    // When a threatened species goes dark, it loses its colour and fades into the deep water
    vec3 darkGhost = vec3(0.06, 0.15, 0.21) * (0.5 + 0.5 * sun);
    col = mix(darkGhost, col, smoothstep(0.05, 0.95, vGlow));
    float alpha = mix(0.22, 1.0, smoothstep(0.0, 0.85, vGlow));
    gl_FragColor = vec4(col, alpha);
  }
`;

function buildSeabedMesh(timeUniform) {
  const nx = hang.nx;
  const ny = hang.ny;
  const xs = hang.x;
  const ys = hang.y;
  const zs = hang.z;
  const pos = new Float32Array(nx * ny * 3);
  for (let ix = 0; ix < nx; ix++) {
    for (let iy = 0; iy < ny; iy++) {
      const k = (ix * ny + iy) * 3;
      pos[k] = xs[ix];
      pos[k + 1] = zs[ix][iy];
      pos[k + 2] = -ys[iy];
    }
  }
  const indices = [];
  for (let ix = 0; ix < nx - 1; ix++) {
    for (let iy = 0; iy < ny - 1; iy++) {
      const a = ix * ny + iy;
      const b = (ix + 1) * ny + iy;
      const c = ix * ny + (iy + 1);
      const d = (ix + 1) * ny + (iy + 1);
      indices.push(a, b, c, b, d, c);
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  const material = new THREE.ShaderMaterial({
    vertexShader: seabedVertex,
    fragmentShader: seabedFragment,
    uniforms: { uTime: timeUniform },
    side: THREE.DoubleSide,
  });
  return new THREE.Mesh(geometry, material);
}

function buildWaterColumnEnclosure(timeUniform) {
  const group = new THREE.Group();
  const maxX = hang.x[hang.nx - 1];
  const maxY = hang.y[hang.ny - 1];
  const surfaceY = 268;

  // Shimmering sea surface at 0 m depth
  const surfGeo = new THREE.PlaneGeometry(maxX, maxY, 56, 56);
  surfGeo.rotateX(-Math.PI / 2);
  surfGeo.translate(maxX / 2, surfaceY, -maxY / 2);
  const surfMat = new THREE.ShaderMaterial({
    vertexShader: surfaceVertex,
    fragmentShader: surfaceFragment,
    uniforms: { uTime: timeUniform },
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,
  });
  group.add(new THREE.Mesh(surfGeo, surfMat));

  // Volumetric sunbeams (god-rays) penetrating the sunlit upper zone
  const rayCanvas = document.createElement('canvas');
  rayCanvas.width = 64;
  rayCanvas.height = 128;
  const rctx = rayCanvas.getContext('2d');
  const rgrad = rctx.createLinearGradient(0, 0, 0, 128);
  rgrad.addColorStop(0, 'rgba(175, 248, 255, 0.28)');
  rgrad.addColorStop(0.45, 'rgba(110, 215, 235, 0.11)');
  rgrad.addColorStop(1, 'rgba(40, 140, 175, 0)');
  rctx.fillStyle = rgrad;
  rctx.fillRect(0, 0, 64, 128);
  const rayTex = new THREE.CanvasTexture(rayCanvas);
  const rayGroup = new THREE.Group();
  for (let i = 0; i < 6; i++) {
    const w = 36 + (i % 3) * 14;
    const h = 115 + (i % 2) * 28;
    const rayGeo = new THREE.PlaneGeometry(w, h);
    const rayMat = new THREE.MeshBasicMaterial({
      map: rayTex,
      transparent: true,
      opacity: 0.52,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      side: THREE.DoubleSide,
    });
    const ray = new THREE.Mesh(rayGeo, rayMat);
    ray.position.set(38 + i * 44, surfaceY - h * 0.46, -235 + (i % 3) * 48);
    ray.rotation.z = -0.16;
    ray.rotation.y = (i % 2 ? 1 : -1) * 0.28;
    rayGroup.add(ray);
  }
  group.add(rayGroup);

  // Subtle translucent side walls of the ocean slice so the depth profile reads clearly
  const sideWall = xIndex => {
    const xVal = hang.x[xIndex];
    const verts = [];
    const idx = [];
    for (let iy = 0; iy < hang.ny; iy++) {
      const zVal = -hang.y[iy];
      const floorY = hang.z[xIndex][iy];
      verts.push(xVal, floorY, zVal, xVal, surfaceY, zVal);
      if (iy < hang.ny - 1) {
        const base = iy * 2;
        idx.push(base, base + 1, base + 2, base + 1, base + 3, base + 2);
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(verts, 3));
    geo.setIndex(idx);
    const mat = new THREE.MeshBasicMaterial({
      color: 0x3aa6bc,
      transparent: true,
      opacity: 0.055,
      depthWrite: false,
      side: THREE.DoubleSide,
    });
    return new THREE.Mesh(geo, mat);
  };
  group.add(sideWall(0), sideWall(hang.nx - 1));

  // Subtle horizontal depth reference lines on the ocean volume sides (0 m, 200 m, 500 m, 1000 m)
  const linePositions = [];
  for (const depthM of [0, 200, 500, 1000]) {
    const y = 263.52 - 0.20108 * depthM;
    linePositions.push(0, y, -maxY, 0, y, 0, maxX, y, -maxY, maxX, y, 0, 0, y, 0, maxX, y, 0);
  }
  const lineGeo = new THREE.BufferGeometry();
  lineGeo.setAttribute('position', new THREE.Float32BufferAttribute(linePositions, 3));
  group.add(
    new THREE.LineSegments(
      lineGeo,
      new THREE.LineBasicMaterial({ color: 0x8be2ee, transparent: true, opacity: 0.18 })
    )
  );

  // Drifting underwater marine snow / plankton particles
  const pCount = 260;
  const pPos = new Float32Array(pCount * 3);
  for (let i = 0; i < pCount; i++) {
    const rx = ((i * 73) % 1000) / 1000;
    const rz = ((i * 137) % 1000) / 1000;
    const ry = ((i * 251) % 1000) / 1000;
    const ix = Math.min(hang.nx - 1, Math.floor(rx * hang.nx));
    const iy = Math.min(hang.ny - 1, Math.floor(rz * hang.ny));
    const floorY = hang.z[ix][iy] + 6;
    pPos[i * 3] = rx * maxX;
    pPos[i * 3 + 1] = floorY + ry * Math.max(8, surfaceY - 4 - floorY);
    pPos[i * 3 + 2] = -rz * maxY;
  }
  const pGeo = new THREE.BufferGeometry();
  pGeo.setAttribute('position', new THREE.BufferAttribute(pPos, 3));
  const pMat = new THREE.PointsMaterial({
    map: glowMap,
    color: 0xbaf6ff,
    size: 3.4,
    transparent: true,
    opacity: 0.38,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  const snow = new THREE.Points(pGeo, pMat);
  group.add(snow);

  return { group, rayGroup, snow };
}

function hash01(seed) {
  const h = Math.sin(seed * 12.9898 + 78.233) * 43758.5453;
  return h - Math.floor(h);
}

// Slide 4: real sea with 109 swimming sharks
function createOceanView(host) {
  const canvas = host.querySelector('canvas');
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: 'high-performance' });
    renderer.setClearColor(0x000000, 0);
  } catch (error) {
    host.classList.add('fallback');
    return;
  }

  host.dataset.litCount = '109';
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(34, 1, 1, 3000);
  const root = new THREE.Group();
  const content = new THREE.Group();
  scene.add(root);
  root.add(content);

  const timeUniform = { value: 0 };
  const seabed = buildSeabedMesh(timeUniform);
  const enclosure = buildWaterColumnEnclosure(timeUniform);
  content.add(seabed, enclosure.group);

  // Center the 300 x 268 x 280 ocean volume at the origin
  const center = new THREE.Vector3(149.2, 138.0, -139.8);
  const radius = 232;
  content.position.copy(center).multiplyScalar(-1);
  root.rotation.y = -0.22;
  root.rotation.x = 0.05;

  // Build the 109 sharks grouped by taxonomic silhouette (formen.ts)
  const sharkMaterial = new THREE.ShaderMaterial({
    vertexShader: sharkVertex,
    fragmentShader: sharkFragment,
    uniforms: { uTime: timeUniform },
    transparent: true,
    side: THREE.DoubleSide,
  });

  const groups = new Map();
  const sharkItems = [];

  source.leds.forEach((led, index) => {
    const rec = recordById.get(led.id) || {
      led: led.id,
      order: 'Carcharhiniformes',
      family: '',
      tier: tiers.get(led.id) || 'LC',
      depth_m: 200,
    };
    const tier = rec.tier || 'LC';
    const shapeKey = formName(rec.order || 'Carcharhiniformes', rec.family || '');
    if (!groups.has(shapeKey)) groups.set(shapeKey, []);

    const r1 = hash01(led.id);
    const r2 = hash01(led.id + 317);
    const r3 = hash01(led.id + 911);

    // Position the shark in the open water column in front of the seabed slope at its true depth
    const rawX = led.position[0];
    const rawY = led.position[1];
    const slopeZ = led.position[2]; // negative (-280 at coast to 0 at deep sea)
    const openWaterRoom = Math.max(14, Math.min(135, -8 - slopeZ));
    const swimZ = Math.min(-12, slopeZ + 16 + (0.12 + 0.72 * r2) * openWaterRoom);
    const rx = 9.5 + r1 * 6.5;
    const rz = 3.2 + r3 * 2.8;
    const anchorX = Math.max(14 + rx, Math.min(284 - rx, rawX + (r1 - 0.5) * 10));
    const anchorY = Math.max(14, Math.min(258, rawY + 3));
    const anchorZ = Math.max(-265 + rz, Math.min(-10 - rz, swimZ));

    // Soft bioluminescent species halo that swims with the shark
    const glowMaterial = new THREE.SpriteMaterial({
      map: glowMap,
      color: colors[tier],
      transparent: true,
      opacity: 0.72,
      depthWrite: false,
      depthTest: false,
      blending: THREE.AdditiveBlending,
      toneMapped: false,
    });
    const glow = new THREE.Sprite(glowMaterial);
    glow.scale.set(15, 15, 1);
    content.add(glow);

    const item = {
      id: led.id,
      tier,
      rank: ranks[tier]++,
      index,
      shapeKey,
      anchor: new THREE.Vector3(anchorX, anchorY, anchorZ),
      rx,
      rz,
      speed: (0.45 + r1 * 0.35) * (index % 2 === 0 ? 1 : -1),
      phase: r2 * Math.PI * 2,
      baseScale: 13.8 + r3 * 3.2,
      glow,
      glowMaterial,
      dark: false,
      darkSince: 0,
      curGlow: 1,
      curFlash: 0,
      curScale: 1,
      curSink: 0,
    };
    sharkItems.push(item);
    groups.get(shapeKey).push(item);
  });

  const instancedBatches = [];
  const tempColor = new THREE.Color();
  for (const [shapeKey, items] of groups.entries()) {
    const geo = formGeometrie(FORMEN[shapeKey]);
    const phases = new Float32Array(items.length);
    items.forEach((it, k) => {
      phases[k] = it.phase / (Math.PI * 2);
    });
    geo.setAttribute('aPhase', new THREE.InstancedBufferAttribute(phases, 1));
    const aGlow = new THREE.InstancedBufferAttribute(new Float32Array(items.length).fill(1), 1);
    const aFlash = new THREE.InstancedBufferAttribute(new Float32Array(items.length).fill(0), 1);
    aGlow.setUsage(THREE.DynamicDrawUsage);
    aFlash.setUsage(THREE.DynamicDrawUsage);
    geo.setAttribute('aGlow', aGlow);
    geo.setAttribute('aFlash', aFlash);

    const mesh = new THREE.InstancedMesh(geo, sharkMaterial, items.length);
    mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    items.forEach((it, k) => {
      mesh.setColorAt(k, tempColor.setHex(colors[it.tier]));
    });
    mesh.frustumCulled = false;
    content.add(mesh);
    instancedBatches.push({ mesh, items, aGlow, aFlash });
  }

  // Expose state to window.SagamiModel.setLights
  sharkItems.forEach(item => ledState.push(item));

  const cameraDirection = new THREE.Vector3(0.82, 0.42, 1.56).normalize();
  camera.near = radius / 100;
  camera.far = radius * 10;

  let dragging = false, x = 0, y = 0, yaw = -0.22, pitch = 0.05;
  canvas.addEventListener('pointerdown', event => {
    dragging = true;
    x = event.clientX;
    y = event.clientY;
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener('pointermove', event => {
    if (!dragging) return;
    yaw = Math.max(-0.95, Math.min(0.65, yaw + (event.clientX - x) * 0.006));
    pitch = Math.max(-0.22, Math.min(0.32, pitch + (event.clientY - y) * 0.004));
    x = event.clientX;
    y = event.clientY;
    root.rotation.set(pitch, yaw, 0);
  });
  canvas.addEventListener('pointerup', () => (dragging = false));
  canvas.addEventListener('pointercancel', () => (dragging = false));

  const resize = () => {
    const rect = host.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    renderer.setPixelRatio(Math.min(devicePixelRatio, 1.7));
    renderer.setSize(rect.width, rect.height, false);
    camera.aspect = rect.width / rect.height;
    const vertical = THREE.MathUtils.degToRad(camera.fov);
    const horizontal = 2 * Math.atan(Math.tan(vertical / 2) * camera.aspect);
    const distance = (radius / Math.sin(Math.min(vertical, horizontal) / 2)) * 0.96;
    camera.position.copy(cameraDirection).multiplyScalar(distance);
    camera.lookAt(0, -4, 0);
    camera.updateProjectionMatrix();
  };
  new ResizeObserver(resize).observe(host);
  resize();
  host.classList.add('ready');

  const dummy = new THREE.Object3D();
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');

  function updateOcean(nowMs) {
    const t = reducedMotion.matches ? 0 : nowMs * 0.001;
    timeUniform.value = t;

    if (!dragging && !reducedMotion.matches) {
      root.rotation.set(pitch + Math.sin(t * 0.35) * 0.012, yaw + Math.sin(t * 0.22) * 0.025, 0);
    }
    enclosure.snow.position.y = Math.sin(t * 0.4) * 2.5;

    for (const { mesh, items, aGlow, aFlash } of instancedBatches) {
      items.forEach((it, k) => {
        const darkDuration = it.dark ? (nowMs - it.darkSince) * 0.001 : 0;
        const isSustainedDark = it.dark && darkDuration > 0.65;
        const isBlinkOff = it.dark && !isSustainedDark;

        const targetGlow = it.dark ? 0.06 : 1.0;
        const targetFlash = !it.dark && nowMs - it.darkSince < 650 && it.darkSince > 0 ? 0.85 : 0.0;
        const targetScale = isSustainedDark ? 0.68 : isBlinkOff ? 0.88 : 1.0;
        const targetSink = isSustainedDark ? 14.0 : 0.0;

        it.curGlow += (targetGlow - it.curGlow) * 0.18;
        it.curFlash += (targetFlash - it.curFlash) * 0.22;
        it.curScale += (targetScale - it.curScale) * 0.14;
        it.curSink += (targetSink - it.curSink) * 0.08;

        const ang = it.phase + t * it.speed;
        const dir = Math.sign(it.speed);
        const px = it.anchor.x + Math.cos(ang) * it.rx;
        const pz = it.anchor.z + Math.sin(ang) * it.rz;
        const py = Math.max(10, it.anchor.y + Math.sin(t * 1.1 + it.phase) * 1.6 - it.curSink);

        const tx = -Math.sin(ang) * it.rx * dir;
        const tz = Math.cos(ang) * it.rz * dir;

        dummy.position.set(px, py, pz);
        dummy.rotation.set(0, Math.atan2(-tz, tx), Math.sin(ang) * 0.06 * dir);
        dummy.scale.setScalar(it.baseScale * it.curScale);
        dummy.updateMatrix();
        mesh.setMatrixAt(k, dummy.matrix);

        it.glow.position.set(px, py, pz);
        it.glowMaterial.opacity = it.dark ? 0.03 : 0.72 + it.curFlash * 0.25;
        it.glow.scale.setScalar(it.dark ? 5 : 15 + it.curFlash * 6);

        aGlow.setX(k, it.curGlow);
        aFlash.setX(k, it.curFlash);
      });
      mesh.instanceMatrix.needsUpdate = true;
      aGlow.needsUpdate = true;
      aFlash.needsUpdate = true;
    }
  }

  updateOcean(performance.now());
  views.push({ host, renderer, scene, camera, update: updateOcean });
}

document.querySelectorAll('.model-view').forEach(host => {
  if (host.dataset.model === 'cycle') createOceanView(host);
  else createBoardView(host);
});

function animate(now) {
  if (!document.hidden) {
    views.forEach(view => {
      const slide = view.host.closest('.slide');
      if (slide.classList.contains('active') || matchMedia('(max-width: 800px)').matches) {
        if (view.update) view.update(now);
        view.renderer.render(view.scene, view.camera);
      }
    });
  }
  requestAnimationFrame(animate);
}
requestAnimationFrame(animate);

window.SagamiModel = {
  setLights(off) {
    const now = performance.now();
    litCount = 0;
    ledState.forEach(item => {
      const dark = Boolean(off(item.tier, item.rank, item.index));
      if (!dark) litCount++;
      if (dark !== item.dark) {
        item.dark = dark;
        item.darkSince = now;
      }
    });
    const host = document.querySelector('[data-model="cycle"]');
    if (host) host.dataset.litCount = String(litCount);
  },
  getState() {
    return { litCount, total: ledState.length, counts: { ...ranks } };
  },
  counts: Object.fromEntries(Object.entries(ranks)),
};
