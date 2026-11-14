"""Build the real coast for the screen: web/src/data/kueste.json.

    /opt/anaconda3/bin/python3 scripts/build_kueste.py

Inputs (in the repo, no internet):
  data/raw/bathymetrie/sagami_grid.csv       SRTM15+ heights of Sagami Bay, land and sea
  data/processed/sagami_profil.csv           the transect the wooden model is cut from
  modell/export/laser_v1/led_montage.csv     LED depth and position across the model

Output: the height grid, the rectangle of the model strip and one point per LED
(lat, lon) where the real seabed lies at the species' depth.

The strip is 1,350 m wide (300 mm at 1 cm = 45 m). Placing 109 sharks inside it would
stack them on top of each other, so across the strip the species are spread over
SPREAD times its width, in the order of their x_mm on the model. Along the slope
nothing is moved: every point sits where the grid reaches the species' depth.

Exit 1 if a check fails.
"""

import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
GRID = ROOT / "data" / "raw" / "bathymetrie" / "sagami_grid.csv"
PROFIL = ROOT / "data" / "processed" / "sagami_profil.csv"
LEDS = ROOT / "modell" / "export" / "laser_v1" / "led_montage.csv"
OUT = ROOT / "web" / "src" / "data" / "kueste.json"

MODEL_WIDTH_MM = 300.0
M_PER_MODEL_MM = 4.5          # 1 cm on the model = 45 m
SPREAD = 6.0                  # sharks spread across SPREAD x the strip width
KM_PER_DEG_LAT = 111.32
TOLERANCE_M = 25.0
EXPECTED_SHAPE = (145, 109)
EXPECTED_LAND = 2811


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def read_csv(path):
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def load_grid():
    with GRID.open(newline="") as fh:
        rows = list(csv.reader(fh))[2:]  # two header lines: names, units
    a = np.array([[float(v) for v in r] for r in rows])
    lats = np.unique(a[:, 0])
    lons = np.unique(a[:, 1])
    if (len(lats), len(lons)) != EXPECTED_SHAPE:
        fail(f"grid is {len(lats)} x {len(lons)}, expected {EXPECTED_SHAPE}")
    # rows run lat-major (lat outer, lon inner), checked here rather than assumed
    z = a[:, 2].reshape(len(lats), len(lons))
    if not (np.allclose(a[: len(lons), 1], lons) and np.allclose(a[:: len(lons), 0], lats)):
        fail("grid rows are not lat-major")
    return lats, lons, z


def bilinear(lats, lons, z, lat, lon):
    """Height in m at (lat, lon); the same interpolation as web/src/szene/koordinaten.ts."""
    fi = (lat - lats[0]) / (lats[1] - lats[0])
    fj = (lon - lons[0]) / (lons[1] - lons[0])
    i = min(max(int(math.floor(fi)), 0), len(lats) - 2)
    j = min(max(int(math.floor(fj)), 0), len(lons) - 2)
    ti = min(max(fi - i, 0.0), 1.0)
    tj = min(max(fj - j, 0.0), 1.0)
    a = z[i, j] * (1 - tj) + z[i, j + 1] * tj
    b = z[i + 1, j] * (1 - tj) + z[i + 1, j + 1] * tj
    return a * (1 - ti) + b * ti


def contour_point(lats, lons, z, lon, depth, lat_start):
    """Walking south from lat_start along lon: the first point where the seabed reaches depth."""
    step = 0.01 / KM_PER_DEG_LAT  # 10 m
    lat = lat_start
    prev = lat
    while lat > lats[0]:
        if -bilinear(lats, lons, z, lat, lon) >= depth:
            lo, hi = lat, prev  # bisection between the last shallower and the first deeper point
            for _ in range(30):
                mid = (lo + hi) / 2
                if -bilinear(lats, lons, z, mid, lon) >= depth:
                    lo = mid
                else:
                    hi = mid
            return lo
        prev = lat
        lat -= step
    return None


def main():
    lats, lons, z = load_grid()
    land = int((z > 0).sum())
    if land != EXPECTED_LAND:
        fail(f"{land} land cells, expected {EXPECTED_LAND}")
    crossings = int(np.sum(np.diff(np.sign(z), axis=1) != 0))
    if crossings == 0:
        fail("no coastline (no 0 m crossing) in the grid")

    profil = read_csv(PROFIL)
    lat_coast = float(profil[0]["lat"])
    lat_end = float(profil[-1]["lat"])
    lon_strip = float(profil[0]["lon"])
    km_per_deg_lon = KM_PER_DEG_LAT * math.cos(math.radians((lat_coast + lat_end) / 2))
    width_km = MODEL_WIDTH_MM * M_PER_MODEL_MM / 1000
    half_deg = width_km / 2 / km_per_deg_lon
    strip = {
        "lat_coast": lat_coast, "lat_end": lat_end,
        "lon_w": lon_strip - half_deg, "lon_e": lon_strip + half_deg,
        "width_km": width_km,
    }
    if not (lats[0] < lat_end < lat_coast < lats[-1] and lons[0] < strip["lon_w"] < strip["lon_e"] < lons[-1]):
        fail("model strip lies outside the grid")

    leds = read_csv(LEDS)
    if len(leds) != 109 or sorted(int(r["led_id"]) for r in leds) != list(range(1, 110)):
        fail("led_montage.csv does not hold LEDs 1-109")

    # start the walk a little inland of the strip's coast point, so shallow species find the shore
    lat_start = lat_coast + 1.0 / KM_PER_DEG_LAT
    punkte = []
    worst = 0.0
    for r in leds:
        led = int(r["led_id"])
        depth = float(r["depth_m"])
        x = float(r["x_mm"])
        dx_km = (x - MODEL_WIDTH_MM / 2) / MODEL_WIDTH_MM * width_km * SPREAD
        lon = lon_strip + dx_km / km_per_deg_lon
        lat = contour_point(lats, lons, z, lon, depth, lat_start)
        if lat is None:
            fail(f"LED {led}: no seabed at {depth} m south of {lat_start:.4f} N along {lon:.4f} E")
        floor = -bilinear(lats, lons, z, lat, lon)
        worst = max(worst, abs(floor - depth))
        if abs(floor - depth) > TOLERANCE_M:
            fail(f"LED {led}: seabed {floor:.0f} m at the point, species depth {depth:.0f} m")
        punkte.append({"led": led, "lat": round(lat, 6), "lon": round(lon, 6), "depth_m": depth})

    out = {
        "source": "SRTM15+ (sagami_grid.csv); strip from sagami_profil.csv; LEDs from led_montage.csv",
        "lat0": float(lats[0]), "dlat": float(lats[1] - lats[0]), "nlat": len(lats),
        "lon0": float(lons[0]), "dlon": float(lons[1] - lons[0]), "nlon": len(lons),
        "km_per_deg_lat": KM_PER_DEG_LAT, "km_per_deg_lon": round(km_per_deg_lon, 4),
        "z": [int(round(v)) for v in z.ravel()],
        "strip": strip,
        "spread": SPREAD,
        "leds": sorted(punkte, key=lambda p: p["led"]),
    }
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    print(f"OK grid {len(lats)}x{len(lons)}, {land} land cells, {crossings} coast crossings")
    print(f"OK strip {lat_coast}..{lat_end} N, {strip['lon_w']:.5f}..{strip['lon_e']:.5f} E, {width_km} km wide")
    print(f"OK 109 LEDs on their depth, worst {worst:.2f} m off; wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
