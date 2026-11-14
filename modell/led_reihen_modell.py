"""Calculate the 8 horizontal LED strip rows (S1..S8 for 8 Arduino pins), generate 3D STL clip-rails, and export CSV/JSON/Arduino header.

Usage:
  /usr/bin/python3 modell/led_reihen_modell.py
"""
import csv
import json
import math
import pathlib
import shutil
import struct

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "export" / "laser_v1"
STL_DIR = OUT / "stl_led_reihen"

WIDTH = 300.0
THICK = 2.0
N_PLATES = 18
PITCH_RAIL = (WIDTH - THICK) / (N_PLATES - 1)  # 17.5294 mm
X_RAILS = [k * PITCH_RAIL + THICK / 2 for k in range(N_PLATES)]  # S-L, P01..P16, S-R
X_GAPS = [X_RAILS[k] + PITCH_RAIL / 2 for k in range(N_PLATES - 1)]  # 17 gaps (1..17)
PITCH_LED = 1000.0 / 60.0  # 16.6667 mm (60 LEDs/m WS2812B strip)
X_LEDS = [150.0 + (g - 8) * PITCH_LED for g in range(17)]  # 17 LEDs centered on model width
CROSS_Y = [21.9, 54.9, 95.2, 145.8, 264.8]  # Q1..Q5


def load_curves():
    d3 = json.loads((OUT / "teile_3d.json").read_text(encoding="utf-8"))
    parts = {p["id"]: p for p in d3["parts"]}
    top_curves = {}
    for pid, p in parts.items():
        if p["kind"] not in ("strip", "side"):
            continue
        ext = p["exterior"]
        top = []
        for u, z in ext:
            if not top or u > top[-1][0]:
                top.append((u, z))
            else:
                break
        top_curves[pid] = top
    return top_curves, d3


def interp_curve(pts, y):
    for (u0, z0), (u1, z1) in zip(pts, pts[1:]):
        if u0 <= y <= u1:
            return z0 if u1 == u0 else z0 + (y - u0) / (u1 - u0) * (z1 - z0)
    return pts[-1][1] if y >= pts[-1][0] else pts[0][1]


def assign_rows_and_slots():
    mont = list(csv.DictReader(open(OUT / "led_montage.csv", encoding="utf-8")))
    master = {int(r["led_id"]): r for r in csv.DictReader(
        open(ROOT / "data" / "processed" / "hai_tiefenmodell_master.csv", encoding="utf-8"))}
    top_curves, _ = load_curves()

    for r in mont:
        r["_id"] = int(r["led_id"])
        r["_y"] = float(r["y_mm"])
        r["_z"] = float(r["z_oberflaeche_mm"])
        r["_d"] = float(r["depth_m"])
        r["_g"] = int(r["luecke"])  # 1..17
        r["master_row"] = int(master[r["_id"]]["row"])

    # 8 LED strips (S1..S8) driven by 8 Arduino pins (Pin 2..9)
    row_defs = [
        ("S1", 2, 248.0, "Q4..Q5 (Oberer Schelf)",  "Q5", 264.8 - 248.0,   0.0,  38.0),  # 12 Haie (3..37.5 m)
        ("S2", 3, 231.0, "Q4..Q5 (Schelf)",         "Q5", 264.8 - 231.0,  38.0,  76.0),  # 15 Haie (40..76 m)
        ("S3", 4, 214.0, "Q4..Q5 (Schelfkante)",    "Q5", 264.8 - 214.0,  76.0, 148.0),  # 15 Haie (90..147.5 m)
        ("S4", 5, 197.0, "Q4..Q5 (Oberer Hang)",    "Q4", 197.0 - 145.8, 148.0, 297.0),  # 15 Haie (150..296.2 m)
        ("S5", 6, 179.0, "Q4..Q5 (Mittlerer Hang)", "Q4", 179.0 - 145.8, 297.0, 405.0),  # 16 Haie (300..402 m)
        ("S6", 7, 161.0, "Q4..Q5 (Hang vor Q4)",    "Q4", 161.0 - 145.8, 405.0, 585.0),  # 14 Haie (407.5..581.5 m)
        ("S7", 8, 125.0, "Q3..Q4 (Tiefhang)",       "Q4", 145.8 - 125.0, 585.0, 750.0),  # 12 Haie (600..708.8 m)
        ("S8", 9,  42.0, "Q1..Q2 (Tiefsee-Canyon)", "Q2",  54.9 -  42.0, 750.0, 1300.0), # 10 Haie (802.2..1272.5 m)
    ]

    by_d = sorted(mont, key=lambda r: (r["_d"], r["_id"]))
    rows_out = []
    sharks_out = []

    for sid, pin, y_row, zone_label, ref_q, dist_q, d0, d1 in row_defs:
        grp = [r for r in by_d if d0 < r["_d"] <= d1]

        # Optimal order-preserving matching of n_s sharks to 17 gap slots (1..17)
        grp_sorted = sorted(grp, key=lambda r: (r["_g"], r["_d"], r["_id"]))
        n_s = len(grp_sorted)
        INF = 1e9
        dp = [[INF] * 18 for _ in range(n_s + 1)]
        parent = [[0] * 18 for _ in range(n_s + 1)]
        for j in range(18):
            dp[0][j] = 0.0
        for i in range(1, n_s + 1):
            orig_g = grp_sorted[i - 1]["_g"]
            for j in range(i, 18):
                cost = abs(j - orig_g)
                if dp[i - 1][j - 1] + cost < dp[i][j - 1]:
                    dp[i][j] = dp[i - 1][j - 1] + cost
                    parent[i][j] = j
                else:
                    dp[i][j] = dp[i][j - 1]
                    parent[i][j] = parent[i][j - 1]
        chosen_gaps = [0] * n_s
        curr_j = 17
        for i in range(n_s, 0, -1):
            g_chosen = parent[i][curr_j]
            chosen_gaps[i - 1] = g_chosen
            curr_j = g_chosen - 1

        rail_zs = [interp_curve(top_curves[f"P{k:02d}"], y_row) for k in range(1, 17)]
        z_mean = sum(rail_zs) / len(rail_zs)
        z_min, z_max = min(rail_zs), max(rail_zs)

        for r, g_new in zip(grp_sorted, chosen_gaps):
            p_left = "S-L" if g_new == 1 else f"P{g_new - 1:02d}"
            p_right = "S-R" if g_new == 17 else f"P{g_new:02d}"
            z_surf = 0.5 * (interp_curve(top_curves[p_left], y_row) + interp_curve(top_curves[p_right], y_row))
            sharks_out.append({
                "strang": sid,
                "arduino_pin": pin,
                "led_id": r["_id"],
                "species": r["species"],
                "farbe": r["farbe"],
                "ansteuerung": r["ansteuerung"],
                "depth_m": r["_d"],
                "luecke": g_new,
                "led_index_0_16": g_new - 1,
                "led_nr_1_17": g_new,
                "x_gap_mm": round(X_GAPS[g_new - 1], 2),
                "x_led_mm": round(X_LEDS[g_new - 1], 2),
                "y_strang_mm": round(y_row, 1),
                "z_papier_mm": round(z_surf, 1),
                "z_led_unten_mm": round(z_surf - 20.0, 1),
                "orig_luecke": r["_g"],
                "orig_y_mm": round(r["_y"], 1),
                "orig_z_mm": round(r["_z"], 1),
            })

        ds = [r["_d"] for r in grp_sorted]
        rows_out.append({
            "strang": sid,
            "arduino_pin": pin,
            "zone": zone_label,
            "anzahl_aktive_leds": n_s,
            "leds_im_modell_1_17": 17,
            "tiefe_min_m": min(ds),
            "tiefe_max_m": max(ds),
            "y_mm": round(y_row, 1),
            "bezug_querband": f"{dist_q:.1f} mm zu {ref_q}",
            "z_oberflaeche_mittel_mm": round(z_mean, 1),
            "z_oberflaeche_bereich_mm": f"{z_min:.1f}..{z_max:.1f}",
            "z_unten_clip_mittel_mm": round(z_mean - 20.0, 1),
            "aktive_luecken": " ".join(str(g) for g in chosen_gaps),
        })

    assert len(sharks_out) == 109
    return rows_out, sharks_out, top_curves


def box_tris(x0, x1, y0, y1, z0, z1):
    v = [
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
    ]
    faces = [
        (0, 2, 1), (0, 3, 2),
        (4, 5, 6), (4, 6, 7),
        (0, 1, 5), (0, 5, 4),
        (2, 3, 7), (2, 7, 6),
        (0, 4, 7), (0, 7, 3),
        (1, 2, 6), (1, 6, 5),
    ]
    return [(v[a], v[b], v[c]) for a, b, c in faces]


def write_binary_stl(path, tris, header_text="LED_Strang_Halter"):
    path.parent.mkdir(parents=True, exist_ok=True)
    hdr = header_text.encode("ascii", errors="ignore")[:80].ljust(80, b"\0")
    buf = [hdr, struct.pack("<I", len(tris))]
    for p0, p1, p2 in tris:
        ux, uy, uz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
        vx, vy, vz = p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]
        nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        L = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
        nx, ny, nz = nx / L, ny / L, nz / L
        buf.append(struct.pack("<12fH", nx, ny, nz, *p0, *p1, *p2, 0))
    path.write_bytes(b"".join(buf))


def build_universal_clip_stl():
    tris = []
    x_min, x_max = 2.5, 297.5
    y_min, y_max = -6.0, 6.0
    groove_y = 5.2

    tris += box_tris(x_min, x_max, y_min, y_max, -4.5, -2.5)
    tris += box_tris(x_min, x_max, y_min, -groove_y, -2.5, 0.0)
    tris += box_tris(x_min, x_max, groove_y, y_max, -2.5, 0.0)

    slot_w = 2.05
    jaw_w = 1.8
    clip_h = 10.0
    for k in range(1, 17):
        xr = X_RAILS[k]
        tris += box_tris(xr - slot_w / 2 - jaw_w, xr - slot_w / 2, y_min, y_max, 0.0, clip_h)
        tris += box_tris(xr + slot_w / 2, xr + slot_w / 2 + jaw_w, y_min, y_max, 0.0, clip_h)

    tris += box_tris(x_min, x_min + 2.0, y_min, y_max, 0.0, clip_h)
    tris += box_tris(x_max - 2.0, x_max, y_min, y_max, 0.0, clip_h)

    wall_t = 1.2
    for g in range(17):
        xl = (x_min + 2.0) if g == 0 else (X_RAILS[g] + slot_w / 2 + jaw_w)
        xr = (x_max - 2.0) if g == 16 else (X_RAILS[g + 1] - slot_w / 2 - jaw_w)
        if xr > xl:
            tris += box_tris(xl, xr, y_min, y_min + wall_t, 0.0, 8.0)
            tris += box_tris(xl, xr, y_max - wall_t, y_max, 0.0, 8.0)

    out_stl = STL_DIR / "led_reihen_universal_clip.stl"
    write_binary_stl(out_stl, tris, "LED_Reihen_Universal_Clip_296mm")
    return out_stl, len(tris)


def build_profile_matched_stl(rows_out, top_curves):
    all_tris = []
    slot_w = 2.05
    jaw_w = 1.6
    y_half = 5.8

    for r in rows_out:
        sid = r["strang"]
        yc = r["y_mm"]
        y0, y1 = yc - y_half, yc + y_half
        row_tris = []

        z_rails = [interp_curve(top_curves[pid], yc) for pid in (["S-L"] + [f"P{k:02d}" for k in range(1, 17)] + ["S-R"])]
        z_bots = [max(0.0, z - 20.0) for z in z_rails]

        for g in range(17):
            xl = 2.5 if g == 0 else (X_RAILS[g] + slot_w / 2)
            xr = 297.5 if g == 16 else (X_RAILS[g + 1] - slot_w / 2)
            zb = 0.5 * (z_bots[g] + z_bots[g + 1])
            zt = 0.5 * (z_rails[g] + z_rails[g + 1]) - 1.5

            row_tris += box_tris(xl - (0 if g == 0 else slot_w / 2),
                                 xr + (0 if g == 16 else slot_w / 2),
                                 y0, y1, zb - 4.0, zb - 2.0)
            row_tris += box_tris(xl - (0 if g == 0 else slot_w / 2),
                                 xr + (0 if g == 16 else slot_w / 2),
                                 y0, yc - 5.2, zb - 2.0, zb)
            row_tris += box_tris(xl - (0 if g == 0 else slot_w / 2),
                                 xr + (0 if g == 16 else slot_w / 2),
                                 yc + 5.2, y1, zb - 2.0, zb)

            chim_top = max(zb + 8.0, zt - 2.0)
            row_tris += box_tris(xl, xl + jaw_w, y0, y1, zb, chim_top)
            row_tris += box_tris(xr - jaw_w, xr, y0, y1, zb, chim_top)
            row_tris += box_tris(xl + jaw_w, xr - jaw_w, y0, y0 + 1.2, zb, chim_top)
            row_tris += box_tris(xl + jaw_w, xr - jaw_w, y1 - 1.2, y1, zb, chim_top)

        write_binary_stl(STL_DIR / f"led_traeger_{sid}.stl", row_tris, f"LED_Traeger_{sid}")
        all_tris += row_tris

    write_binary_stl(STL_DIR / "led_straenge_alle_8_im_modell.stl", all_tris, "LED_Straenge_S1_S8")
    return len(all_tris)


def write_arduino_mapping(rows_out, sharks_out):
    """Write an Arduino header mapping each led_id (1..109) to (strang_index 0..7, pixel_index 0..16)."""
    by_id = {s["led_id"]: s for s in sharks_out}
    lines = [
        "// Automatisch generiert von modell/led_reihen_modell.py",
        "// 8 WS2812B LED-Straenge (S1..S8) an 8 Arduino-Pins (Pin 2..9), je 17 aktive Luecken (0..16).",
        "#pragma once",
        "#include <Arduino.h>",
        "",
        "const uint8_t N_STRIPS = 8;",
        "const uint8_t LEDS_PER_STRIP = 24; // mind. 17 im Modell + Ueberhang am Streifenende",
        "const uint8_t STRIP_PINS[N_STRIPS] = {2, 3, 4, 5, 6, 7, 8, 9};",
        "",
        "// Zuordnung fuer jede Haiart (Index = led_id - 1, fuer led_id 1..109):",
        "// LED_STRIP_OF[i] = Strang 0..7 (S1..S8), LED_PIXEL_OF[i] = LED-Position 0..16 (Luecke 1..17)",
        "const uint8_t LED_STRIP_OF[109] PROGMEM = {",
    ]
    for i in range(0, 109, 12):
        chunk = [str(int(by_id[k]["strang"][1:]) - 1) for k in range(i + 1, min(110, i + 13))]
        lines.append("  " + ", ".join(chunk) + ",")
    lines.append("};")
    lines.append("")
    lines.append("const uint8_t LED_PIXEL_OF[109] PROGMEM = {")
    for i in range(0, 109, 12):
        chunk = [str(by_id[k]["led_index_0_16"]) for k in range(i + 1, min(110, i + 13))]
        lines.append("  " + ", ".join(chunk) + ",")
    lines.append("};")
    out_h = ROOT / "arduino" / "hai_zeitreise" / "acht_straenge_map.h"
    out_h.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    if STL_DIR.exists():
        shutil.rmtree(STL_DIR)
    STL_DIR.mkdir(parents=True, exist_ok=True)

    rows_out, sharks_out, top_curves = assign_rows_and_slots()

    with open(OUT / "led_reihen_uebersicht.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
        w.writeheader()
        w.writerows(rows_out)

    with open(OUT / "led_reihen_montage.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(sharks_out[0].keys()))
        w.writeheader()
        w.writerows(sharks_out)

    with open(OUT / "led_reihen_3d.json", "w", encoding="utf-8") as f:
        json.dump({"rows": rows_out, "sharks": sharks_out, "x_rails": X_RAILS, "x_gaps": X_GAPS, "x_leds": X_LEDS},
                  f, ensure_ascii=False, indent=1)

    write_arduino_mapping(rows_out, sharks_out)
    u_stl, n_u = build_universal_clip_stl()
    n_all = build_profile_matched_stl(rows_out, top_curves)
    print(f"Wrote {len(rows_out)} LED strips (S1..S8) and {len(sharks_out)} shark signals.")
    print(f"Universal clip STL: {u_stl} ({n_u} tris), all 8 profile STLs ({n_all} tris).")
    for r in rows_out:
        print(f"  {r['strang']} (Pin {r['arduino_pin']}): {r['anzahl_aktive_leds']:2d} aktive LEDs | "
              f"Tiefe {r['tiefe_min_m']:6.1f}..{r['tiefe_max_m']:6.1f} m | "
              f"y={r['y_mm']:5.1f} mm ({r['bezug_querband']}) | z_papier={r['z_oberflaeche_mittel_mm']:5.1f} mm")


if __name__ == "__main__":
    main()
