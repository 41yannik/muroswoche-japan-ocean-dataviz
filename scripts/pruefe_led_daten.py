"""Check the Arduino data headers against the model CSVs (read-only).

Run after every regeneration of zeitreihe.h or acht_straenge_map.h:
    /opt/anaconda3/bin/python3 scripts/pruefe_led_daten.py
Exit code 0 = all checks pass, 1 = at least one mismatch.
"""

import csv
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKETCH = ROOT / "arduino" / "hai_zeitreise"
MAP_H = SKETCH / "acht_straenge_map.h"
SERIES_H = SKETCH / "zeitreihe.h"
MONTAGE_CSV = ROOT / "modell" / "export" / "laser_v1" / "led_reihen_montage.csv"
MASTER_CSV = ROOT / "data" / "processed" / "hai_tiefenmodell_master.csv"

# Same mapping as scripts/build_zeitreihe_led.py
COLORS = {"blau": 0x0050FF, "gelb": 0xFFC000, "orange": 0xFF5000, "rot": 0xFF0000}
N_GAPS = 17


def strip_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def scalar(text, name):
    m = re.search(rf"\b{name}\s*=\s*(\d+)\s*;", text)
    if not m:
        raise ValueError(f"constant {name} not found")
    return int(m.group(1))


def array(text, name):
    """All integers of a (possibly nested) initialised array, in order."""
    m = re.search(rf"\b{name}\s*(?:\[[^\]]*\])+\s*(?:PROGMEM\s*)?=\s*\{{", text)
    if not m:
        raise ValueError(f"array {name} not found")
    depth, i = 1, m.end()
    while depth:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    body = text[m.end():i - 1]
    return [int(tok, 0) for tok in re.findall(r"0x[0-9A-Fa-f]+|\d+", body)]


def main():
    errors = []

    def check(ok, msg):
        if not ok:
            errors.append(msg)

    map_h = strip_comments(MAP_H.read_text())
    ser_h = strip_comments(SERIES_H.read_text())

    n_strips = scalar(map_h, "N_STRIPS")
    leds_per_strip = scalar(map_h, "LEDS_PER_STRIP")
    pins = array(map_h, "STRIP_PINS")
    strip_of = array(map_h, "LED_STRIP_OF")
    pixel_of = array(map_h, "LED_PIXEL_OF")

    n_led = scalar(ser_h, "N_LED")
    n_years = scalar(ser_h, "N_YEARS")
    n_stock = scalar(ser_h, "N_STOCK")
    n_scen = scalar(ser_h, "N_SCEN")
    colors = array(ser_h, "LED_COLOR")
    stock_ids = array(ser_h, "STOCK_LED_ID")
    bright = array(ser_h, "BRIGHT")
    flags = array(ser_h, "FLAGS")
    rest = array(ser_h, "REST_BRIGHT")

    # Sizes
    check(len(pins) == n_strips, f"STRIP_PINS has {len(pins)} entries, N_STRIPS={n_strips}")
    check(len(set(pins)) == len(pins), f"STRIP_PINS not unique: {pins}")
    check(len(strip_of) == n_led, f"LED_STRIP_OF has {len(strip_of)} entries, N_LED={n_led}")
    check(len(pixel_of) == n_led, f"LED_PIXEL_OF has {len(pixel_of)} entries, N_LED={n_led}")
    check(len(colors) == n_led, f"LED_COLOR has {len(colors)} entries, N_LED={n_led}")
    check(len(stock_ids) == n_stock, f"STOCK_LED_ID has {len(stock_ids)} entries")
    check(len(rest) == n_stock, f"REST_BRIGHT has {len(rest)} entries")
    want = n_scen * n_stock * n_years
    check(len(bright) == want, f"BRIGHT has {len(bright)} values, expected {want}")
    check(len(flags) == want, f"FLAGS has {len(flags)} values, expected {want}")
    check(all(f < 16 for f in flags), "FLAGS uses bits above bit3")
    check(leds_per_strip >= N_GAPS,f"LEDS_PER_STRIP={leds_per_strip} < {N_GAPS}")

    # Slots: valid range and unique
    for i, (s, p) in enumerate(zip(strip_of, pixel_of)):
        check(s < n_strips, f"led_id {i + 1}: strand {s} out of range")
        check(p < N_GAPS, f"led_id {i + 1}: pixel {p} out of range 0..16")
    slots = Counter(zip(strip_of, pixel_of))
    dup = [k for k, v in slots.items() if v > 1]
    check(not dup, f"duplicate slots (strand, pixel): {dup}")

    # Header map vs assembly CSV
    with MONTAGE_CSV.open(newline="") as fh:
        montage = list(csv.DictReader(fh))
    check(len(montage) == n_led, f"montage CSV has {len(montage)} rows, N_LED={n_led}")
    seen = set()
    for row in montage:
        lid = int(row["led_id"])
        check(lid not in seen, f"montage CSV: led_id {lid} twice")
        seen.add(lid)
        if not 1 <= lid <= n_led:
            check(False, f"montage CSV: led_id {lid} out of range")
            continue
        s = int(row["strang"].lstrip("S")) - 1
        p = int(row["led_index_0_16"])
        check(strip_of[lid - 1] == s, f"led_id {lid}: header strand S{strip_of[lid - 1] + 1}, CSV {row['strang']}")
        check(pixel_of[lid - 1] == p, f"led_id {lid}: header pixel {pixel_of[lid - 1]}, CSV {p}")
        if 0 <= s < len(pins):
            check(pins[s] == int(row["arduino_pin"]), f"led_id {lid}: CSV pin {row['arduino_pin']}, header pin {pins[s]}")
        check(COLORS.get(row["farbe"]) == colors[lid - 1], f"led_id {lid}: CSV colour {row['farbe']} differs from LED_COLOR")
    missing = sorted(set(range(1, n_led + 1)) - seen)
    check(not missing, f"montage CSV: led_id missing: {missing}")

    # Colours vs master CSV
    with MASTER_CSV.open(newline="") as fh:
        master = {int(r["led_id"]): r for r in csv.DictReader(fh)}
    check(sorted(master) == list(range(1, n_led + 1)), "master CSV led_id is not 1..N_LED")
    for lid, row in master.items():
        if 1 <= lid <= n_led:
            check(COLORS.get(row["farbe"]) == colors[lid - 1], f"led_id {lid}: master colour {row['farbe']} differs from LED_COLOR")

    # Stocks: the set must equal the species with a stock status in the master
    # CSV, and the order (index into BRIGHT/FLAGS) must match the species names
    # the generator writes in the comment line after STOCK_LED_ID.
    for sid in stock_ids:
        check(1 <= sid <= n_led, f"stock led_id {sid} out of range")
    marked = sorted(lid for lid, r in master.items() if r["bestand_ratio"].strip())
    check(sorted(stock_ids) == marked, f"STOCK_LED_ID {stock_ids} differs from master stocks {marked}")
    m = re.search(r"STOCK_LED_ID\[[^\]]*\]\s*=\s*\{[^}]*\};\s*\n\s*//\s*([^\n]+)", SERIES_H.read_text())
    names = [n.strip() for n in m.group(1).split(",")] if m else []
    want_names = [master[sid]["species"] for sid in stock_ids if sid in master]
    check(names == want_names, f"stock order: header comment {names}, master species {want_names}")

    per_strand = Counter(strip_of)
    print(f"species: {n_led}, slots unique: {len(slots)}, LEDS_PER_STRIP: {leds_per_strip}")
    print("per strand: " + ", ".join(f"S{s + 1}(pin {pins[s]})={per_strand[s]}" for s in range(n_strips)))
    for sid in stock_ids:
        if 1 <= sid <= n_led:
            name = master.get(sid, {}).get("species", "?")
            print(f"stock {sid:3d} {name}: S{strip_of[sid - 1] + 1} LED {pixel_of[sid - 1] + 1}")

    if errors:
        print(f"\nFAIL: {len(errors)} problem(s)")
        for e in errors[:50]:
            print("  - " + e)
        return 1
    print("\nOK: headers match the model CSVs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
