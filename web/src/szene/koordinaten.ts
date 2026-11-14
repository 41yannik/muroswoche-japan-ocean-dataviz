// Real Sagami Bay (kueste.json, SRTM15+) in scene units.
// 1 unit = 100 m across the ground. Heights are exaggerated EXAG times, so the slope reads
// on screen: a depth of 1,000 m is 40 units down. X runs east, Z runs south (towards a
// camera on the open sea), Y is up with the sea surface at 0.
import * as THREE from "three";
import kueste from "../data/kueste.json";

export const UNIT_M = 100;
export const EXAG = 4;
/** scene units per metre of depth or height */
export const Y_PER_M = EXAG / UNIT_M;

const LAT_C = kueste.lat0 + ((kueste.nlat - 1) * kueste.dlat) / 2;
const LON_C = kueste.lon0 + ((kueste.nlon - 1) * kueste.dlon) / 2;
const X_PER_DEG = (kueste.km_per_deg_lon * 1000) / UNIT_M;
const Z_PER_DEG = (kueste.km_per_deg_lat * 1000) / UNIT_M;
const Z = kueste.z as number[];

export const GRID = { nlat: kueste.nlat, nlon: kueste.nlon };

export function szeneX(lon: number): number {
  return (lon - LON_C) * X_PER_DEG;
}

export function szeneZ(lat: number): number {
  return -(lat - LAT_C) * Z_PER_DEG;
}

export function lonAusX(x: number): number {
  return LON_C + x / X_PER_DEG;
}

export function latAusZ(z: number): number {
  return LAT_C - z / Z_PER_DEG;
}

/** Height in metres at grid cell (i lat, j lon). */
export function zelle(i: number, j: number): number {
  return Z[i * kueste.nlon + j];
}

/** Height in metres at (lat, lon), bilinear; the same interpolation as scripts/build_kueste.py. */
export function hoehe(lat: number, lon: number): number {
  const fi = (lat - kueste.lat0) / kueste.dlat;
  const fj = (lon - kueste.lon0) / kueste.dlon;
  const i = Math.min(Math.max(Math.floor(fi), 0), kueste.nlat - 2);
  const j = Math.min(Math.max(Math.floor(fj), 0), kueste.nlon - 2);
  const ti = Math.min(Math.max(fi - i, 0), 1);
  const tj = Math.min(Math.max(fj - j, 0), 1);
  const a = zelle(i, j) * (1 - tj) + zelle(i, j + 1) * tj;
  const b = zelle(i + 1, j) * (1 - tj) + zelle(i + 1, j + 1) * tj;
  return a * (1 - ti) + b * ti;
}

/** Ground height in scene units under scene point (x, z). */
export function bodenY(x: number, z: number): number {
  return hoehe(latAusZ(z), lonAusX(x)) * Y_PER_M;
}

export function szenePunkt(lat: number, lon: number, hoeheM: number, out = new THREE.Vector3()): THREE.Vector3 {
  return out.set(szeneX(lon), hoeheM * Y_PER_M, szeneZ(lat));
}

/** Corners of the block in scene units. */
export const RAND = {
  x0: szeneX(kueste.lon0),
  x1: szeneX(kueste.lon0 + (kueste.nlon - 1) * kueste.dlon),
  z0: szeneZ(kueste.lat0 + (kueste.nlat - 1) * kueste.dlat), // north edge
  z1: szeneZ(kueste.lat0), // south edge
};

export const STREIFEN = kueste.strip;
export const LED_ORTE = kueste.leds;
