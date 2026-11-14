"""Build the JSON data for the screen visualization in web/src/data/.

    /opt/anaconda3/bin/python3 scripts/build_web_daten.py

Inputs (all already in the repo, no internet):
  data/processed/hai_tiefenmodell_master.csv   species, order, Red List category, depth
  data/processed/hai_namen.csv                  English / Japanese names (scripts/hole_artnamen.py)
  data/processed/hai_zeitreihe_led.csv          SSB/SSB_MSY series for the four stock species
  modell/export/laser_v1/led_montage.csv        LED position on the model (scaled mm)
  modell/export/laser_v1/oberflaeche_05mm.npz   unscaled surface height grid

Outputs: arten.json, hang.json, zeitreihe.json. Exit 1 if a check fails
(109 species, LED numbers 1-109, tier counts CR 4 / EN 19 / VU 23 / rest 63).
"""

import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
LASER = ROOT / "modell" / "export" / "laser_v1"
OUT = ROOT / "web" / "src" / "data"

WIDTH_MM = 300.0      # scaled model width, same as modell/laser_schnitte.py
GRID_EVERY = 5        # keep every 5th sample of the 0.5 mm grid -> 2.5 mm unscaled
DEPTH_MARKS_M = [200, 500, 1000]
TIER_OF = {"CR": "CR", "EN": "EN", "VU": "VU", "-": "LC"}
EXPECTED_TIERS = {"CR": 4, "EN": 19, "VU": 23, "LC": 63}


def read_csv(path):
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def build_arten():
    master = read_csv(PROC / "hai_tiefenmodell_master.csv")
    names = {r["led_id"]: r for r in read_csv(PROC / "hai_namen.csv")}
    pos = {r["led_id"]: r for r in read_csv(LASER / "led_montage.csv")}
    arten = []
    for r in master:
        led = r["led_id"]
        p, n = pos.get(led), names.get(led)
        if p is None or n is None:
            fail(f"LED {led} missing in led_montage.csv or hai_namen.csv")
        if p["species"] != r["species"] or n["species"] != r["species"]:
            fail(f"LED {led}: species differs between the input files")
        if r["category"] not in TIER_OF:
            fail(f"LED {led}: unknown category {r['category']!r}")
        arten.append({
            "led": int(led),
            "species": r["species"],
            "name_en": n["name_en"],
            "name_ja": n["name_ja"],
            "order": r["order"],
            "family": r["family"],
            "tier": TIER_OF[r["category"]],
            "depth_m": float(r["depth_m"]),
            "x": round(float(p["x_mm"]), 2),
            "y": round(float(p["y_mm"]), 2),
            "z": round(float(p["z_oberflaeche_mm"]), 2),
            "wiki_url": r["wiki_url"],
        })
    leds = sorted(a["led"] for a in arten)
    if len(arten) != 109 or leds != list(range(1, 110)):
        fail(f"expected LEDs 1-109 once each, got {len(arten)} rows")
    counts = {t: sum(1 for a in arten if a["tier"] == t) for t in EXPECTED_TIERS}
    if counts != EXPECTED_TIERS:
        fail(f"tier counts {counts} != {EXPECTED_TIERS}")
    return sorted(arten, key=lambda a: a["led"]), counts


def build_hang(arten):
    d = np.load(LASER / "oberflaeche_05mm.npz")
    scale = WIDTH_MM / float(d["xs"][-1])
    z = d["z"][::GRID_EVERY, ::GRID_EVERY] * scale
    xs = d["xs"][::GRID_EVERY] * scale
    ys = d["ys"][::GRID_EVERY] * scale
    # The model maps depth almost linearly to height (r about -0.985 over the 109 LEDs),
    # so a depth mark is the contour at the fitted height.
    dep = np.array([a["depth_m"] for a in arten])
    hz = np.array([a["z"] for a in arten])
    slope, icept = np.polyfit(dep, hz, 1)
    r = float(np.corrcoef(dep, hz)[0, 1])
    marks = [{"depth_m": m, "z": round(float(icept + slope * m), 2)} for m in DEPTH_MARKS_M]
    return {
        "nx": len(xs), "ny": len(ys),
        "x": [round(float(v), 2) for v in xs],
        "y": [round(float(v), 2) for v in ys],
        "z": [[round(float(v), 1) for v in row] for row in z],   # z[ix][iy]
        "depth_fit": {"z_per_m": round(float(slope), 5), "z_at_0": round(float(icept), 2), "r": round(r, 4)},
        "depth_marks": marks,
    }


def build_zeitreihe(arten):
    led_of = {a["species"]: a["led"] for a in arten}
    if len(led_of) != len(arten):
        fail("species names in the master CSV are not unique")
    rows = read_csv(PROC / "hai_zeitreihe_led.csv")
    out = {}
    for r in rows:
        sp = r["species"]
        if sp not in led_of:
            fail(f"time series species {sp!r} is not in the master CSV")
        s = out.setdefault(sp, {"led": led_of[sp], "observed": [], "forecast": {}, "sources": []})
        pt = {"year": int(r["year"]), "ratio": float(r["ratio"])}
        if math.isnan(pt["ratio"]):
            fail(f"{sp} {r['year']}: ratio is missing")
        for k in ("lo", "hi"):
            v = float(r[k]) if r[k].strip() else math.nan
            if not math.isnan(v):
                pt[k] = v
        if r["bruch"] == "True":
            pt["model_break"] = True
        if r["art"] == "beobachtet":
            s["observed"].append(pt)
        else:
            s["forecast"].setdefault(r["szenario"], []).append(pt)
        src = f'{r["modell"]}: {r["quelle"]}'
        if src not in s["sources"]:
            s["sources"].append(src)
    for s in out.values():
        s["observed"].sort(key=lambda p: p["year"])
        for v in s["forecast"].values():
            v.sort(key=lambda p: p["year"])
    if len(out) != 4:
        fail(f"expected 4 stock species, got {len(out)}")
    with_fc = [sp for sp, s in out.items() if s["forecast"]]
    if with_fc != ["Prionace glauca"]:
        fail(f"forecast expected only for Prionace glauca, got {with_fc}")
    return {
        "measure": "SSB / SSB_MSY (spawning stock relative to the level that supports the maximum sustainable yield)",
        "species": out,
    }


def write(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
    return path, path.stat().st_size


def main():
    arten, counts = build_arten()
    hang = build_hang(arten)
    zr = build_zeitreihe(arten)
    for name, obj in (("arten.json", arten), ("hang.json", hang), ("zeitreihe.json", zr)):
        path, size = write(name, obj)
        print(f"{path.relative_to(ROOT)}: {size} bytes")
    print(f"species 109, tiers {counts}, grid {hang['nx']}x{hang['ny']}, "
          f"depth fit r {hang['depth_fit']['r']}, marks {hang['depth_marks']}")
    for sp, s in zr["species"].items():
        o = s["observed"]
        print(f"  {sp} (LED {s['led']}): observed {o[0]['year']}-{o[-1]['year']}, "
              f"forecast {sorted(s['forecast'])}")
    if any(math.isnan(v) for row in hang["z"] for v in row):
        fail("NaN in the height grid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
