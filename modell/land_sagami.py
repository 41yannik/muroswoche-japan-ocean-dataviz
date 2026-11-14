"""Extracts the real land profile behind the Sagami transect coast from the stored grid.

Run: .venv/bin/python -I modell/land_sagami.py <project_root>
Reads data/raw/bathymetrie/sagami_grid.csv and the transect from data/processed/sagami_profil.csv,
writes data/processed/sagami_land.csv (km inland, elevation m), smoothed like the sea profile.
"""
import csv
import os
import sys

import numpy as np

ROOT = sys.argv[1]
KM_MAX = 3.0
GRID = os.path.join(ROOT, "data/raw/bathymetrie/sagami_grid.csv")
PROF = os.path.join(ROOT, "data/processed/sagami_profil.csv")
OUT = os.path.join(ROOT, "data/processed/sagami_land.csv")

with open(PROF, newline="") as f:
    first = next(csv.DictReader(f))
lon0, coast_lat = float(first["lon"]), float(first["lat"])
with open(GRID) as f:
    rows = [tuple(map(float, l.split(","))) for l in f.read().splitlines()[2:] if l.strip()]
lon = min({r[1] for r in rows}, key=lambda x: abs(x - lon0))
assert abs(lon - lon0) < 1e-3, (lon, lon0)
col = sorted(((r[0], r[2]) for r in rows if r[1] == lon), key=lambda p: p[0])
inland = [((lat - coast_lat) * 111.0, z) for lat, z in col if lat > coast_lat + 1e-6]
km = np.array([0.0] + [k for k, _ in inland])
elev = np.array([0.0] + [z for _, z in inland])          # water line at the coast
assert (elev[1:] > 0).all() or km[np.argmax(elev[1:] <= 0) + 1] > KM_MAX, "sea cell inside land strip"
fine = np.arange(0.0, KM_MAX + 1e-9, 0.05)
e = np.interp(fine, km, elev)
win = 10                                                   # ~0.5 km moving average
pad = np.concatenate([np.full(win, e[0]), e, np.full(win, e[-1])])
smooth = np.convolve(pad, np.ones(win) / win, mode="same")[win:-win]
smooth[0] = 0.0
with open(OUT, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["km_inland", "elev_m", "lat", "lon"])
    for k, z in zip(fine, smooth):
        w.writerow([round(k, 3), round(max(z, 0.0), 1), round(coast_lat + k / 111.0, 5), round(lon, 5)])
print(f"land lon {lon:.4f}, raw km/elev {[(round(a, 2), b) for a, b in zip(km, elev) if a <= KM_MAX + 0.5]}")
print(f"smoothed max {smooth.max():.1f} m at {fine[smooth.argmax()]:.2f} km, wrote {OUT}")
