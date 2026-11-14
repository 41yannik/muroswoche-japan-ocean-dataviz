"""Fetches a real bathymetry transect through Sagami Bay and writes the slope profile.

Run: .venv/bin/python -I modell/fetch_sagami.py <project_root>
Source: SRTM15+ (15 arc-sec) via NOAA ERDDAP, fallback ETOPO1 (1 arc-min).
Picks the north-south line (lon 139.25-139.50) that reaches 1305 m from the
coast with the least counter-rise, so the profile is real but readable.
"""
import csv
import math
import os
import sys
import time
import urllib.request

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = sys.argv[1]
TARGET = 1305.0
LAT0, LAT1, LON0, LON1 = 34.80, 35.40, 139.15, 139.60
LON_MIN, LON_MAX = 139.25, 139.50
SOURCES = [
    ("SRTM15+", "https://coastwatch.pfeg.noaa.gov/erddap/griddap/srtm15plus.csv?z"),
    ("ETOPO1", "https://coastwatch.pfeg.noaa.gov/erddap/griddap/etopo180.csv?altitude"),
]
RAW = os.path.join(ROOT, "data/raw/bathymetrie/sagami_grid.csv")
OUT = os.path.join(ROOT, "data/processed/sagami_profil.csv")
FIG = os.path.join(ROOT, "figures/sagami_profil.png")


def fetch():
    q = f"%5B({LAT0}):1:({LAT1})%5D%5B({LON0}):1:({LON1})%5D"
    for name, base in SOURCES:
        for attempt in range(6):
            try:
                with urllib.request.urlopen(base + q, timeout=120) as r:
                    text = r.read().decode()
                if text.startswith("latitude"):
                    return name, text
            except Exception as e:  # server throttles with 503
                print(f"{name} attempt {attempt + 1}: {e}")
            time.sleep(20)
    sys.exit("no bathymetry source reachable")


name, text = fetch()
os.makedirs(os.path.dirname(RAW), exist_ok=True)
with open(RAW, "w") as f:
    f.write(text)
rows = [tuple(map(float, l.split(","))) for l in text.splitlines()[2:] if l.strip()]
lats = sorted({r[0] for r in rows}, reverse=True)
lons = sorted({r[1] for r in rows})
grid = {(r[0], r[1]): r[2] for r in rows}
print(f"source {name}: {len(lats)} x {len(lons)} cells")

best = None
for lon in lons:
    if not LON_MIN <= lon <= LON_MAX:
        continue
    col = [(lat, -grid[(lat, lon)]) for lat in lats]          # depth positive, north -> south
    land = [i for i, (_, d) in enumerate(col) if d <= 0]
    if not land:
        continue
    start = land[0]
    while start + 1 < len(col) and col[start + 1][1] <= 0:   # last land cell of the coast
        start += 1
    sea = col[start + 1:]
    reach = next((i for i, (_, d) in enumerate(sea) if d >= TARGET), None)
    if reach is None or any(d <= 0 for _, d in sea[:reach + 1]):
        continue
    seg = [(0.0, 0.0)] + [((col[start][0] - lat) * 111.0, d) for lat, d in sea[:reach + 1]]
    rise = sum(max(0.0, seg[i][1] - seg[i + 1][1]) for i in range(len(seg) - 1))
    key = (rise, seg[-1][0])
    if best is None or key < best[0]:
        best = (key, lon, col[start][0], seg)

assert best, "no transect reaches 1305 m"
(rise, length), lon, coast_lat, seg = best
km = np.array([s[0] for s in seg])
dep = np.array([s[1] for s in seg])
# clip at the first crossing of TARGET by linear interpolation
i = int(np.argmax(dep >= TARGET))
km_end = km[i - 1] + (TARGET - dep[i - 1]) / (dep[i] - dep[i - 1]) * (km[i] - km[i - 1])
fine = np.arange(0.0, km_end, 0.05)
d_fine = np.interp(fine, km[: i + 1], dep[: i + 1])
win = max(1, int(round(1.0 / 0.05)))                         # ~1 km moving average
pad = np.concatenate([np.full(win, d_fine[0]), d_fine, np.full(win, d_fine[-1])])
smooth = np.convolve(pad, np.ones(win) / win, mode="same")[win:-win]
smooth[0] = 0.0
fine = np.append(fine, km_end)
smooth = np.append(smooth, TARGET)
smooth = np.clip(smooth, 0.0, TARGET)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["km", "depth_m", "lat", "lon", "source"])
    for k, d in zip(fine, smooth):
        w.writerow([round(k, 3), round(d, 1), round(coast_lat - k / 111.0, 5), round(lon, 5), name])

slope_mm = 275.0
exag = (km_end * 1e6 / slope_mm) / (45.0 * 1000 / 10)
print(f"transect lon {lon:.4f} E, coast at {coast_lat:.4f} N, length {km_end:.2f} km, "
      f"counter-rise {rise:.0f} m, points {len(seg)}")
print(f"km to 50/200/500/1000 m: {[round(float(fine[np.argmax(smooth >= x)]), 2) for x in (50, 200, 500, 1000)]}")
print(f"horizontal 1 mm = {km_end * 1000 / slope_mm:.0f} m, vertical 1 mm = 4.5 m, exaggeration x{exag:.0f}")

os.makedirs(os.path.dirname(FIG), exist_ok=True)
fig, ax = plt.subplots(figsize=(10, 4.5))
ax.plot(km, -dep, ".", color="0.6", label=f"{name} Rohwerte")
ax.plot(fine, -smooth, color="#1f4e8c", lw=2, label="geglättetes Modellprofil")
for d in (200, 500, 1000):
    ax.axhline(-d, color="0.8", lw=0.8, ls="--")
    ax.text(km_end, -d, f" {d} m", va="center", fontsize=8)
ax.set_xlabel(f"Abstand von der Küste (km), Längengrad {lon:.3f}° O, Küste {coast_lat:.3f}° N")
ax.set_ylabel("Tiefe (m)")
ax.set_title(f"Sagami-Bucht: Bodenprofil bis 1.305 m ({km_end:.1f} km), im Modell {exag:.0f}-fach überhöht")
ax.legend(loc="lower left", fontsize=8)
fig.tight_layout()
fig.savefig(FIG, dpi=150)
print("wrote", OUT, FIG)
