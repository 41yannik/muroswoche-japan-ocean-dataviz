#!/usr/bin/env python3
"""Build the shark time series for the LED time-travel display.

Past: RAM Legacy v4.61 SSB/SSBmsy (assessments up to 2014-2016) plus the latest
ISC status points. Future: ISC 2022 blue shark projection table (Table 19,
median SSB per scenario 2021-2030) divided by SSBMSY from Table 18.

Outputs:
  data/processed/hai_zeitreihe_led.csv   long table, one row per species/year/scenario
  arduino/hai_zeitreise/zeitreihe.h      brightness and flag arrays (PROGMEM)
  figures/q07_zeitreise.png              control plot of what the LEDs show

hai_tiefenmodell_master.csv is read, never written.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
ISC_DIR = ROOT / "data" / "raw" / "isc"
BSH_PDF = ISC_DIR / "ISC22_BSH_assessment.pdf"
OUT_CSV = PROCESSED / "hai_zeitreihe_led.csv"
OUT_H = ROOT / "arduino" / "hai_zeitreise" / "zeitreihe.h"
OUT_PNG = ROOT / "figures" / "q07_zeitreise.png"

YEAR0, YEAR1 = 1970, 2030
RATIO_FULL = 2.0  # SSB/SSBMSY at which a pixel is fully bright
GAMMA = 2.2

# RAM stock -> species in the master table. OWSHARCWPAC is excluded: its
# series duplicate BLSHARNPAC in the raw source (checked 2026-11-11).
STOCKS = {
    "BLSHARNPAC": ("Prionace glauca", "Blauhai"),
    "SFMAKONPAC": ("Isurus oxyrinchus", "Makohai"),
    "THRSHARNPAC": ("Alopias vulpinus", "Fuchshai"),
    "SLKSHARCWPAC": ("Carcharhinus falciformis", "Seidenhai"),
}

# Latest published status points (not in RAM). Values from the report tables.
# The blue shark 2020 point is added in build() as SSB2020 / SSBMSY (tonnes,
# Table 18), the same formula as the projection years. The report's headline
# 1.17 is the median of the ratio and would put 2020 on a different scale.
STATUS_POINTS = [
    # species, year, ratio, lo, hi, source
    ("Isurus oxyrinchus", 2022, 1.17, 0.46, 1.92,
     "ISC 2024 SMA, Table ES 1: D2019-2022/DMSY, 95 % Intervall"),
]

# Column order of Table 19 as printed in the report.
BSH_SCENARIOS = ["f_plus20", "f_msy", "f_minus20", "status_quo"]
SCENARIO_LABEL = {
    "status_quo": "Fang wie 2017-2019",
    "f_msy": "Fang auf F_MSY",
    "f_plus20": "Fang +20 %",
    "f_minus20": "Fang -20 %",
}
LED_SCENARIOS = ["status_quo", "f_msy"]  # run 1 and run 2 on the model

# Species without a numeric projection: what we found, stated per species.
NO_FORECAST = {
    "Isurus oxyrinchus": "ISC 2024 nennt nur die Richtung (steigt ausser bei U_MSY), Werte nur als Abbildung ES 6",
    "Alopias vulpinus": "keine Prognose gefunden (RAM-Reihe aus NOAA-Bewertung bis 2014)",
    "Carcharhinus falciformis": "keine Prognose gefunden (WCPFC 2018, Status nur indikativ)",
}


def pdf_text(path: Path) -> str:
    return subprocess.run(["pdftotext", "-layout", str(path), "-"],
                          check=True, capture_output=True, text=True).stdout


def parse_projection_table(text: str, heading: str) -> pd.DataFrame:
    start = text.index(heading)
    rows = []
    for line in text[start:start + 3000].splitlines():
        m = re.match(r"^\s*(20[23]\d)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s*$", line)
        if m:
            rows.append([int(m.group(1))] + [int(g.replace(",", "")) for g in m.groups()[1:]])
    if len(rows) != 10:
        raise SystemExit(f"{heading}: expected 10 projection years, found {len(rows)}")
    return pd.DataFrame(rows, columns=["year"] + BSH_SCENARIOS)


def parse_table18(text: str, pattern: str) -> float:
    start = text.index("Table 18.")
    m = re.search(pattern, text[start:start + 2500])
    if not m:
        raise SystemExit(f"{pattern!r} not found in Table 18")
    return float(m.group(1).replace(",", ""))


def observed_ram() -> pd.DataFrame:
    ts = pd.read_csv(PROCESSED / "ram_timeseries_selected.csv")
    out = []
    for stockid, (species, _) in STOCKS.items():
        d = ts[(ts.stockid == stockid) & ts.SSBdivSSBmsy.notna()]
        for r in d.itertuples():
            out.append(dict(species=species, year=int(r.year), ratio=float(r.SSBdivSSBmsy),
                            lo=np.nan, hi=np.nan, art="beobachtet", szenario="alle",
                            modell=f"RAM v4.61 {stockid}",
                            quelle="RAM Legacy v4.61, SSBdivSSBmsy"))
    return pd.DataFrame(out)


def build() -> pd.DataFrame:
    text = pdf_text(BSH_PDF)
    tab19 = parse_projection_table(text, "Table 19.")
    tabe2 = parse_projection_table(text, "Table E2.")
    if not tab19.equals(tabe2):
        raise SystemExit("Table 19 and Table E2 disagree")
    ssbmsy = parse_table18(text, r"SSBMSY\*\s+t\s+([\d,]+)")
    ssb2020 = parse_table18(text, r"SSB2020\s+t\s+([\d,]+)")
    reported = parse_table18(text, r"SSB2020/SSBMSY\s+([\d.]+)")

    rows = observed_ram()
    points = [("Prionace glauca", 2020, round(ssb2020 / ssbmsy, 4), np.nan, np.nan,
               f"ISC 2022 BSH, Table 18: SSB2020 {ssb2020:.0f} t / SSBMSY {ssbmsy:.0f} t "
               f"(Bericht: Median des Verhaeltnisses {reported}, 80 % 0,570-1,776)")]
    points += STATUS_POINTS
    pts = pd.DataFrame([dict(species=s, year=y, ratio=r, lo=lo, hi=hi, art="beobachtet",
                             szenario="alle", modell=src.split(",")[0], quelle=src)
                        for s, y, r, lo, hi, src in points])
    proj = []
    for sc in BSH_SCENARIOS:
        for r in tab19.itertuples():
            ssb = getattr(r, sc)
            proj.append(dict(species="Prionace glauca", year=r.year, ratio=round(ssb / ssbmsy, 4),
                             lo=np.nan, hi=np.nan, art="prognose", szenario=sc,
                             modell="ISC 2022 BSH",
                             quelle=f"ISC 2022 BSH Table 19 ({SCENARIO_LABEL[sc]}): "
                                    f"SSB {ssb} t / SSBMSY {ssbmsy:.0f} t"))
    df = pd.concat([rows, pts, pd.DataFrame(proj)], ignore_index=True)
    df["unter_msy"] = df.ratio < 1.0
    # A model change between consecutive observed points is a break, not a trend.
    df = df.sort_values(["species", "szenario", "year"]).reset_index(drop=True)
    df["bruch"] = False
    for sp, g in df[df.art == "beobachtet"].groupby("species"):
        prev = g.modell.shift()
        idx = g.index[(prev.notna()) & (g.modell != prev)]
        df.loc[idx, "bruch"] = True
    return df


def species_year_series(df: pd.DataFrame, species: str, scenario: str) -> pd.DataFrame:
    """One value per year YEAR0..YEAR1 for the LED: observed, linear bridge, forecast."""
    obs = df[(df.species == species) & (df.art == "beobachtet")].set_index("year").ratio
    prog = df[(df.species == species) & (df.art == "prognose") & (df.szenario == scenario)]
    prog = prog.set_index("year").ratio
    years = np.arange(YEAR0, YEAR1 + 1)
    s = pd.Series(np.nan, index=years)
    s.update(obs[obs.index.isin(years)])
    kind = pd.Series("", index=years, dtype=object)
    kind[s.notna()] = "beobachtet"
    first, last = obs.index.min(), obs.index.max()
    gap = years[(years > first) & (years < last) & s.isna().values]
    if len(gap):
        s = s.interpolate(limit_area="inside")
        kind[gap] = "bruecke"
    for y, v in prog.items():
        s[y] = v
        kind[y] = "prognose"
    return pd.DataFrame({"ratio": s, "kind": kind})


def to_brightness(ratio: float) -> int:
    if np.isnan(ratio):
        return 0
    x = min(max(ratio / RATIO_FULL, 0.0), 1.0)
    return max(1, int(round(255 * x ** GAMMA)))


def write_header(df: pd.DataFrame) -> None:
    master = pd.read_csv(PROCESSED / "hai_tiefenmodell_master.csv")
    led = master.set_index("species").led_id
    species = [v[0] for v in STOCKS.values()]
    lines = [
        "// Generated by scripts/build_zeitreihe_led.py - do not edit by hand.",
        "// Brightness: SSB/SSBMSY mapped to 0-255 (ratio 2.0 = 255, gamma 2.2); 0 = no data.",
        "// Flags: bit0 data, bit1 forecast, bit2 below MSY, bit3 bridge between two models.",
        "#pragma once",
        "#include <Arduino.h>",
        "",
        f"const uint16_t YEAR_FIRST = {YEAR0};",
        f"const uint16_t YEAR_LAST = {YEAR1};",
        f"const uint8_t N_YEARS = {YEAR1 - YEAR0 + 1};",
        f"const uint8_t N_STOCK = {len(species)};",
        f"const uint8_t N_SCEN = {len(LED_SCENARIOS)};  // 0 = {LED_SCENARIOS[0]}, 1 = {LED_SCENARIOS[1]}",
        "",
        "// led_id from hai_tiefenmodell_master.csv (1-based) for each stock",
        "const uint8_t STOCK_LED_ID[N_STOCK] = {" + ", ".join(str(int(led[s])) for s in species) + "};",
        "// " + ", ".join(species),
        "",
    ]
    bright = []
    flags = []
    rest = []
    for sc in LED_SCENARIOS:
        b_sc, f_sc = [], []
        for sp in species:
            ser = species_year_series(df, sp, sc)
            b_sc.append([to_brightness(v) for v in ser.ratio])
            fl = []
            for v, k in zip(ser.ratio, ser.kind):
                f = 0
                if not np.isnan(v):
                    f |= 1
                    f |= 2 if k == "prognose" else 0
                    f |= 4 if v < 1.0 else 0
                    f |= 8 if k == "bruecke" else 0
                fl.append(f)
            f_sc.append(fl)
        bright.append(b_sc)
        flags.append(f_sc)
    for sp in species:
        last = df[(df.species == sp) & (df.art == "beobachtet")].sort_values("year").iloc[-1]
        rest.append(to_brightness(last.ratio))

    def arr(name, data):
        out = [f"const uint8_t {name}[N_SCEN][N_STOCK][N_YEARS] PROGMEM = {{"]
        for sc, block in zip(LED_SCENARIOS, data):
            out.append(f"  {{ // {sc}")
            for sp, row in zip(species, block):
                out.append("    {" + ",".join(str(v) for v in row) + "}, // " + sp)
            out.append("  },")
        out.append("};")
        return out

    lines += arr("BRIGHT", bright) + [""] + arr("FLAGS", flags) + [""]
    lines.append("// Rest state: latest observed status point per stock")
    lines.append("const uint8_t REST_BRIGHT[N_STOCK] = {" + ", ".join(map(str, rest)) + "};")
    lines.append("")
    colors = {"blau": "0x0050FF", "gelb": "0xFFC000", "orange": "0xFF5000", "rot": "0xFF0000"}
    m = master.sort_values("led_id")
    lines.append("// Red List colour per led_id (index = led_id - 1)")
    lines.append(f"const uint8_t N_LED = {len(m)};")
    lines.append("const uint32_t LED_COLOR[N_LED] PROGMEM = {")
    for i in range(0, len(m), 8):
        chunk = m.farbe.iloc[i:i + 8]
        lines.append("  " + ", ".join(colors[c] for c in chunk) + ",")
    lines.append("};")
    OUT_H.parent.mkdir(parents=True, exist_ok=True)
    OUT_H.write_text("\n".join(lines) + "\n")


def plot(df: pd.DataFrame) -> None:
    species = [v for v in STOCKS.values()]
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), sharex=True, sharey=True)
    for ax, (sp, name) in zip(axes.flat, species):
        for sc, ls in zip(LED_SCENARIOS, ["-", "--"]):
            ser = species_year_series(df, sp, sc)
            for kind, col in [("beobachtet", "#1f4e9c"), ("bruecke", "#999999"), ("prognose", "#d1495b")]:
                y = ser.ratio.where(ser.kind == kind)
                if y.notna().any():
                    ax.plot(ser.index, y, ls if kind == "prognose" else "-", color=col,
                            lw=2, marker="." if kind == "beobachtet" else None, ms=4, label=f"{kind} ({SCENARIO_LABEL[sc]})" if kind == "prognose" else kind)
        pts = df[(df.species == sp) & df.lo.notna()]
        ax.errorbar(pts.year, pts.ratio, yerr=[pts.ratio - pts.lo, pts.hi - pts.ratio],
                    fmt="o", color="black", capsize=3, label="Status mit Intervall")
        ax.axhline(1.0, color="black", lw=0.8, ls=":")
        ax.set_title(name)
        if sp in NO_FORECAST:
            ax.text(0.02, 0.04, NO_FORECAST[sp], transform=ax.transAxes, fontsize=7, wrap=True)
        ax.set_xlim(YEAR0, YEAR1)
    handles, labels = {}, {}
    for ax in axes.flat:
        for h, l in zip(*ax.get_legend_handles_labels()):
            handles.setdefault(l, h)
    fig.legend(handles.values(), handles.keys(), loc="lower center", ncol=3, fontsize=8)
    fig.supylabel("SSB / SSB_MSY (1 = MSY-Grenze)")
    fig.suptitle("Was die LEDs zeigen: Bestand relativ zur MSY-Grenze")
    fig.tight_layout(rect=(0, 0.08, 1, 0.96))
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PNG, dpi=130)


def main() -> None:
    df = build()
    df.to_csv(OUT_CSV, index=False)
    write_header(df)
    plot(df)
    print(f"{OUT_CSV.relative_to(ROOT)}: {len(df)} rows")
    for sp, g in df[df.art == "beobachtet"].groupby("species"):
        last = g.sort_values("year").iloc[-1]
        print(f"  {sp}: {g.year.min()}-{g.year.max()}, last {last.ratio:.3f} ({last.modell})")
    p = df[(df.art == "prognose") & (df.year == 2030)]
    print("  Blauhai 2030:", {r.szenario: round(r.ratio, 3) for r in p.itertuples()})
    print(f"{OUT_H.relative_to(ROOT)} and {OUT_PNG.relative_to(ROOT)} written")


if __name__ == "__main__":
    main()
