"""Create a 3-page LEGO-style visual assembly instruction PDF (A4 landscape).

Usage: /usr/bin/python3 modell/laser_anleitung_pdf.py
Writes:
  modell/export/laser_v1/zusammenbau_anleitung.pdf
  modell/export/laser_v1/斜面模型_切断用_600x300_20261112/00_Zusammenbau_Anleitung.pdf
"""
import json
import math
import pathlib
import re
import zlib

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "export" / "laser_v1"
DELIV = OUT / "斜面模型_切断用_600x300_20261112"

W_PT, H_PT = 841.89, 595.28


def pdf_escape(s):
    b = s.encode("cp1252", errors="replace")
    out = []
    for ch in b:
        if ch in (40, 41, 92):
            out.append(92)
            out.append(ch)
        elif 32 <= ch <= 126:
            out.append(ch)
        else:
            out.extend(f"\\{ch:03o}".encode("ascii"))
    return bytes(out).decode("ascii")


class Canvas:
    def __init__(self):
        self.ops = []

    def stroke_rgb(self, r, g, b):
        self.ops.append(f"{r:.3f} {g:.3f} {b:.3f} RG")

    def fill_rgb(self, r, g, b):
        self.ops.append(f"{r:.3f} {g:.3f} {b:.3f} rg")

    def line_width(self, w):
        self.ops.append(f"{w:.3f} w")

    def dash(self, arr=(), phase=0):
        inner = " ".join(f"{x:g}" for x in arr)
        self.ops.append(f"[{inner}] {phase:g} d")

    def rect(self, x, y, w, h, fill=False, stroke=True):
        op = "B" if (fill and stroke) else ("f" if fill else "S")
        self.ops.append(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re {op}")

    def line(self, x1, y1, x2, y2):
        self.ops.append(f"{x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")

    def poly(self, pts, close=True, fill=False, stroke=True, even_odd=False):
        if not pts:
            return
        segs = [f"{pts[0][0]:.2f} {pts[0][1]:.2f} m"]
        for x, y in pts[1:]:
            segs.append(f"{x:.2f} {y:.2f} l")
        if close:
            segs.append("h")
        if fill and stroke:
            segs.append("B*" if even_odd else "B")
        elif fill:
            segs.append("f*" if even_odd else "f")
        else:
            segs.append("S")
        self.ops.append(" ".join(segs))

    def compound_poly(self, rings, fill=True, stroke=True):
        segs = []
        for pts in rings:
            if not pts:
                continue
            segs.append(f"{pts[0][0]:.2f} {pts[0][1]:.2f} m")
            for x, y in pts[1:]:
                segs.append(f"{x:.2f} {y:.2f} l")
            segs.append("h")
        op = "B*" if (fill and stroke) else ("f*" if fill else "S")
        segs.append(op)
        self.ops.append(" ".join(segs))

    def circle(self, cx, cy, r, fill=True, stroke=False):
        k = 0.55228475 * r
        self.ops.append(
            f"{cx + r:.2f} {cy:.2f} m "
            f"{cx + r:.2f} {cy + k:.2f} {cx + k:.2f} {cy + r:.2f} {cx:.2f} {cy + r:.2f} c "
            f"{cx - k:.2f} {cy + r:.2f} {cx - r:.2f} {cy + k:.2f} {cx - r:.2f} {cy:.2f} c "
            f"{cx - r:.2f} {cy - k:.2f} {cx - k:.2f} {cy - r:.2f} {cx:.2f} {cy - r:.2f} c "
            f"{cx + k:.2f} {cy - r:.2f} {cx + r:.2f} {cy - k:.2f} {cx + r:.2f} {cy:.2f} c "
            + ("B" if (fill and stroke) else ("f" if fill else "S"))
        )

    def arrow(self, x1, y1, x2, y2, head=5.5, color=(0.85, 0.12, 0.12), lw=1.6):
        self.stroke_rgb(*color)
        self.fill_rgb(*color)
        self.line_width(lw)
        self.line(x1, y1, x2, y2)
        ang = math.atan2(y2 - y1, x2 - x1)
        a1 = ang + math.pi - 0.48
        a2 = ang - math.pi + 0.48
        self.poly(
            [(x2, y2), (x2 + head * math.cos(a1), y2 + head * math.sin(a1)),
             (x2 + head * math.cos(a2), y2 + head * math.sin(a2))],
            close=True, fill=True, stroke=False
        )

    def text(self, x, y, s, size=10, bold=False, color=(0.1, 0.1, 0.12), align="left"):
        font = "/F2" if bold else "/F1"
        if align in ("center", "right"):
            w = sum(0.55 if c.isupper() else (0.28 if c in "il.,:;|!I1 " else 0.50) for c in s) * size
            if bold:
                w *= 1.05
            x = x - (w / 2 if align == "center" else w)
        r, g, b = color
        self.ops.append(
            f"BT {font} {size:.2f} Tf {r:.3f} {g:.3f} {b:.3f} rg "
            f"{x:.2f} {y:.2f} Td ({pdf_escape(s)}) Tj ET"
        )

    def step_badge(self, cx, cy, num_str, bg=(0.10, 0.36, 0.68), r=12):
        self.fill_rgb(*bg)
        self.circle(cx, cy, r, fill=True, stroke=False)
        self.text(cx, cy - 4.5, num_str, size=13, bold=True, color=(1, 1, 1), align="center")

    def stream_bytes(self):
        return ("\n".join(self.ops) + "\n").encode("ascii")


def point_in_poly(x, y, poly):
    inside = False
    n = len(poly)
    for i in range(n - 1):
        x1, y1 = poly[i]
        x2, y2 = poly[i + 1]
        if ((y1 > y) != (y2 > y)) and (x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-12) + x1):
            inside = not inside
    return inside


def find_label_pos(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    best = (0, (minx + maxx) / 2, (miny + maxy) / 2)
    for frac in [0.5, 0.45, 0.55, 0.4, 0.6, 0.35, 0.65, 0.3, 0.7]:
        x = minx + frac * (maxx - minx)
        in_y = [miny + (k / 80.0) * (maxy - miny) for k in range(81)]
        inside_ys = [y for y in in_y if point_in_poly(x, y, pts)]
        if inside_ys:
            runs = []
            cur = [inside_ys[0]]
            step = (maxy - miny) / 80.0 * 1.5
            for y in inside_ys[1:]:
                if y - cur[-1] <= step:
                    cur.append(y)
                else:
                    runs.append(cur)
                    cur = [y]
            runs.append(cur)
            longest = max(runs, key=lambda r: r[-1] - r[0])
            span = longest[-1] - longest[0]
            if span > best[0]:
                best = (span, x, 0.5 * (longest[0] + longest[-1]))
    return best[1], best[2]


def iso_pt(x, y, z, ox, oy, sc):
    a = math.radians(25)
    b = math.radians(30)
    px = ox + sc * (x * math.cos(a) + y * math.cos(b))
    py = oy + sc * (-x * math.sin(a) + y * math.sin(b) + z)
    return px, py


def draw_header(c, page_num, subtitle):
    c.fill_rgb(0.10, 0.16, 0.24)
    c.rect(0, H_PT - 44, W_PT, 44, fill=True, stroke=False)
    c.text(20, H_PT - 23, "LEGO-BAUANLEITUNG: HANGMODELL SAGAMI-BUCHT (24 TEILE, 5 BRETTER)",
           size=13.5, bold=True, color=(1, 1, 1))
    c.text(20, H_PT - 37, subtitle, size=8.6, color=(0.82, 0.88, 0.96))
    c.text(W_PT - 20, H_PT - 29, f"Seite {page_num} / 3",
           size=10.5, bold=True, color=(0.98, 0.82, 0.32), align="right")


def draw_mini_part(c, pts_2d, bx, by, bw, bh, fill_col, stroke_col):
    xs = [p[0] for p in pts_2d]
    ys = [p[1] for p in pts_2d]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    w = max(maxx - minx, 1.0)
    h = max(maxy - miny, 1.0)
    sc = min(bw / w, bh / h)
    ox = bx + (bw - w * sc) / 2 - minx * sc
    oy = by + (bh - h * sc) / 2 - miny * sc
    c.fill_rgb(*fill_col)
    c.stroke_rgb(*stroke_col)
    c.line_width(0.6)
    c.poly([(ox + x * sc, oy + y * sc) for x, y in pts_2d], close=True, fill=True, stroke=True)


def draw_assembly_3d(c, parts, ox, oy, sc, existing_ids, active_ids, lift_z=None, show_q_labels=False, show_p_labels=()):
    """Draw a LEGO-style 3D step where existing_ids are muted grey/beige and active_ids are vibrant."""
    lift_z = lift_z or {}

    def style_for(pid, is_active):
        kind = parts[pid]["kind"]
        if not is_active:
            if kind == "floor":
                return (0.93, 0.91, 0.86), (0.70, 0.66, 0.58), 0.6
            return (0.88, 0.90, 0.92), (0.64, 0.68, 0.73), 0.55
        if kind == "floor":
            return (0.90, 0.82, 0.66), (0.48, 0.38, 0.22), 1.0
        if kind == "side":
            return (0.20, 0.48, 0.80), (0.08, 0.25, 0.48), 1.0
        if kind == "cross":
            return (0.95, 0.50, 0.18), (0.68, 0.25, 0.05), 0.9
        return (0.18, 0.72, 0.54), (0.06, 0.42, 0.30), 0.85

    all_ids = list(existing_ids) + list(active_ids)

    # 1. Floor B
    if "B" in all_ids:
        fc, sc_col, lw = style_for("B", "B" in active_ids)
        dz = lift_z.get("B", 0.0)
        pts = [iso_pt(u, v, dz, ox, oy, sc) for u, v in parts["B"]["exterior"]]
        c.fill_rgb(*fc)
        c.stroke_rgb(*sc_col)
        c.line_width(lw)
        c.poly(pts, close=True, fill=True, stroke=True)
        # Draw the 6 floor slots clearly
        for hole in parts["B"]["holes"]:
            hpts = [iso_pt(u, v, dz, ox, oy, sc) for u, v in hole]
            c.fill_rgb(0.25, 0.25, 0.30)
            c.poly(hpts, close=True, fill=True, stroke=False)

    # 2. Left side wall S-L
    if "S-L" in all_ids:
        fc, sc_col, lw = style_for("S-L", "S-L" in active_ids)
        dz = lift_z.get("S-L", 0.0)
        pts = [iso_pt(0.0, u, v + dz, ox, oy, sc) for u, v in parts["S-L"]["exterior"]]
        c.fill_rgb(*fc)
        c.stroke_rgb(*sc_col)
        c.line_width(lw)
        c.poly(pts, close=True, fill=True, stroke=True)
        for hole in parts["S-L"]["holes"]:
            hpts = [iso_pt(0.0, u, v + dz, ox, oy, sc) for u, v in hole]
            c.fill_rgb(1, 1, 1)
            c.stroke_rgb(*sc_col)
            c.line_width(0.5)
            c.poly(hpts, close=True, fill=True, stroke=True)

    # 3. Cross bands Q5..Q1 (back to front)
    for j in range(5, 0, -1):
        qid = f"Q{j}"
        if qid not in all_ids:
            continue
        qp = parts[qid]
        yc = qp["place"]["at"] + 1.0
        dz = lift_z.get(qid, 0.0)
        fc, sc_col, lw = style_for(qid, qid in active_ids)
        pts = [iso_pt(u, yc, v + dz, ox, oy, sc) for u, v in qp["exterior"]]
        c.fill_rgb(*fc)
        c.stroke_rgb(*sc_col)
        c.line_width(lw)
        c.poly(pts, close=True, fill=True, stroke=True)
        if show_q_labels:
            lx, ly = iso_pt(306, yc, qp["exterior"][-1][1] + dz, ox, oy, sc)
            c.text(lx + 2, ly - 2, qid, size=7.2, bold=True,
                   color=(0.72, 0.25, 0.05) if qid in active_ids else (0.45, 0.48, 0.52))

    # 4. Profile strips P01..P16 (left to right)
    for k in range(1, 17):
        pid = f"P{k:02d}"
        if pid not in all_ids:
            continue
        pp = parts[pid]
        xm = pp["place"]["at"] + 1.0
        dz = lift_z.get(pid, 0.0)
        fc, sc_col, lw = style_for(pid, pid in active_ids)
        pts = [iso_pt(xm, u, v + dz, ox, oy, sc) for u, v in pp["exterior"]]
        c.fill_rgb(*fc)
        c.stroke_rgb(*sc_col)
        c.line_width(lw)
        c.poly(pts, close=True, fill=True, stroke=True)
        if pid in show_p_labels:
            top_z = max(v for u, v in pp["exterior"] if u > 275) + dz
            tx, ty = iso_pt(xm, 280.6, top_z + 10, ox, oy, sc)
            c.text(tx, ty, pid, size=6.8, bold=True,
                   color=(0.05, 0.40, 0.28) if pid in active_ids else (0.40, 0.44, 0.48), align="center")

    # 5. Right side wall S-R
    if "S-R" in all_ids:
        dz = lift_z.get("S-R", 0.0)
        is_act = "S-R" in active_ids
        sr_pts = [iso_pt(300.0, u, v + dz, ox, oy, sc) for u, v in parts["S-R"]["exterior"]]
        if is_act:
            c.fill_rgb(0.20, 0.48, 0.80)
            c.stroke_rgb(0.08, 0.25, 0.48)
            c.line_width(1.1)
            c.poly(sr_pts, close=True, fill=True, stroke=True)
            for hole in parts["S-R"]["holes"]:
                hpts = [iso_pt(300.0, u, v + dz, ox, oy, sc) for u, v in hole]
                c.fill_rgb(0.95, 0.50, 0.18)
                c.stroke_rgb(0.08, 0.25, 0.48)
                c.line_width(0.5)
                c.poly(hpts, close=True, fill=True, stroke=True)
        else:
            # Draw dashed outline so inner strips remain visible
            c.stroke_rgb(0.25, 0.45, 0.68)
            c.line_width(1.1)
            c.dash((3, 2), 0)
            c.poly(sr_pts, close=True, fill=False, stroke=True)
            c.dash()


# ---------------------------------------------------------------------------
# PAGE 1: SCHRITT 1 (Teile auf Brett 01..05 beschriften + Komplett-Legende)
# ---------------------------------------------------------------------------
def build_page1(c, d3, metrics):
    draw_header(
        c, 1,
        "SCHRITT 1 (VORBEREITUNG): Teile noch im Holzbrett laut Lageplan mit Kreppband/Bleistift beschriften!"
    )

    parts_meta = {p["id"]: p for p in d3["parts"]}
    kind_fill = {
        "floor": (0.90, 0.84, 0.73),
        "side": (0.65, 0.82, 0.96),
        "cross": (0.98, 0.74, 0.52),
        "strip": (0.68, 0.90, 0.80),
    }
    kind_stroke = {
        "floor": (0.45, 0.36, 0.24),
        "side": (0.10, 0.30, 0.58),
        "cross": (0.70, 0.28, 0.06),
        "strip": (0.08, 0.44, 0.32),
    }

    # Top instruction banner for Step 1
    c.fill_rgb(0.99, 0.96, 0.86)
    c.stroke_rgb(0.88, 0.72, 0.30)
    c.line_width(1.0)
    c.rect(20, H_PT - 82, W_PT - 40, 32, fill=True, stroke=True)
    c.step_badge(38, H_PT - 66, "1", bg=(0.85, 0.45, 0.08), r=11)
    c.text(55, H_PT - 63,
           "WARUM ZUERST BESCHRIFTEN? Auf den Holzteilen selbst ist nichts eingraviert. Lege die 5 geschnittenen Bretter genau so vor dich",
           size=8.6, bold=True, color=(0.20, 0.15, 0.05))
    c.text(55, H_PT - 75,
           "wie unten abgebildet (Teile links oben buendig) und schreibe auf jedes Teil mit Bleistift oder Kreppband den Namen (B, S-L, S-R, Q1..Q5, P01..P16)!",
           size=8.3, color=(0.25, 0.20, 0.10))

    col_x = [20, 430]
    row_y = [348, 178, 8]
    box_w, box_h = 392, 162
    sc = 0.46  # 600 * 0.46 = 276 pt, 300 * 0.46 = 138 pt

    for b_info in metrics["bretter"]:
        b = b_info["brett"]
        pids = b_info["teile"]
        col = (b - 1) % 2
        row = (b - 1) // 2
        bx, by = col_x[col], row_y[row]

        c.fill_rgb(0.97, 0.98, 0.99)
        c.stroke_rgb(0.78, 0.82, 0.88)
        c.line_width(0.8)
        c.rect(bx, by, box_w, box_h, fill=True, stroke=True)

        c.step_badge(bx + 14, by + box_h - 12, f"0{b}", bg=(0.12, 0.35, 0.65), r=8.0)
        c.text(bx + 26, by + box_h - 15,
               f"Brett 0{b} (Datei 0{b}_...pdf)  ->  {len(pids)} Teile: {', '.join(pids)}",
               size=8.8, bold=True, color=(0.10, 0.15, 0.24))

        ox, oy = bx + 8, by + 5
        bw_pt, bh_pt = 600.0 * sc, 300.0 * sc
        c.fill_rgb(0.99, 0.97, 0.93)
        c.stroke_rgb(0.62, 0.54, 0.44)
        c.line_width(0.9)
        c.rect(ox, oy, bw_pt, bh_pt, fill=True, stroke=True)

        svg = (OUT / f"brett_{b:02d}.svg").read_text()
        paths = re.findall(r"<path d=\"([^\"]+)\"/>", svg)
        groups = []
        for p in paths:
            pts = [(float(x), float(y)) for x, y in re.findall(r"([-+]?\d*\.?\d+),([-+]?\d*\.?\d+)", p)]
            area = 0.5 * sum(
                pts[k][0] * pts[(k + 1) % len(pts)][1] - pts[(k + 1) % len(pts)][0] * pts[k][1]
                for k in range(len(pts) - 1)
            )
            if area > 0:
                groups.append([pts])
            else:
                groups[-1].append(pts)

        for pid, rings in zip(pids, groups):
            kind = parts_meta[pid]["kind"]
            c.fill_rgb(*kind_fill[kind])
            c.stroke_rgb(*kind_stroke[kind])
            c.line_width(0.7)
            pdf_rings = [[(ox + x * sc, oy + (300.0 - y) * sc) for x, y in r] for r in rings]
            c.compound_poly(pdf_rings, fill=True, stroke=True)

            lx_mm, ly_mm = find_label_pos(rings[0])
            lx_pt = ox + lx_mm * sc
            ly_pt = oy + (300.0 - ly_mm) * sc

            c.fill_rgb(1, 1, 1)
            c.stroke_rgb(*kind_stroke[kind])
            c.line_width(0.6)
            tw = 22 if len(pid) >= 3 else 16
            c.rect(lx_pt - tw / 2, ly_pt - 5, tw, 10, fill=True, stroke=True)
            c.text(lx_pt, ly_pt - 3.0, pid, size=7.8, bold=True, color=(0.08, 0.10, 0.14), align="center")

        # Right side checklist inside board card
        tx = ox + bw_pt + 7
        ty = oy + bh_pt - 9
        c.text(tx, ty, "Abhaken & Beschriften:", size=7.2, bold=True, color=(0.15, 0.20, 0.28))
        for idx_p, pid in enumerate(pids):
            pm = parts_meta[pid]
            if pid == "B":
                where = "Bodenplatte"
            elif pid == "S-L":
                where = "Wand LINKS"
            elif pid == "S-R":
                where = "Wand RECHTS"
            elif pid.startswith("Q"):
                qnum = int(pid[1:])
                where = f"{qnum}. Querband v. vorn"
            else:
                pnum = int(pid[1:])
                where = f"Schlitz {pnum} v. links"
            yy = ty - 12 - idx_p * 12.5
            c.stroke_rgb(0.4, 0.45, 0.5)
            c.rect(tx, yy - 1, 6.5, 6.5, fill=False, stroke=True)
            c.text(tx + 9, yy, f"{pid}: {where}", size=6.8, bold=True, color=(0.12, 0.16, 0.22))

    # 6th box: Quick visual summary of the 4 part types + orientation rule
    bx, by = col_x[1], row_y[2]
    c.fill_rgb(0.97, 0.98, 0.99)
    c.stroke_rgb(0.78, 0.82, 0.88)
    c.line_width(0.8)
    c.rect(bx, by, box_w, box_h, fill=True, stroke=True)
    c.text(bx + 12, by + box_h - 15,
           "Woran erkenne ich oben/unten und vorne/hinten an jedem Teil?",
           size=9.2, bold=True, color=(0.10, 0.15, 0.24))

    rules = [
        ((0.90, 0.84, 0.73), "B (1x Bodenplatte, Brett 01):",
         "Rechteck 312 x 286,6 mm mit 6 Schlitzen (je 3 links fuer S-L und 3 rechts fuer S-R).",
         "Ist symmetrisch -> liegt flach auf dem Tisch."),
        ((0.65, 0.82, 0.96), "S-L & S-R (2x Seitenwaende, Brett 01 & 02):",
         "Unten gerade Kante mit 3 kurzen Zapfen (fuer Boden B). Innen 5 Rechteckloecher (fuer Q1..Q5).",
         "Flaches Ende = VORNE (Tiefsee, y=0)  |  Hohes Ende (27,1 cm) = HINTEN (Kueste)."),
        ((0.98, 0.74, 0.52), "Q1 bis Q5 (5x Querbaender, Brett 02 & 03):",
         "Haben je 16 Schlitze (fuer P01..P16) und links/rechts je 1 Endzapfen (fuer S-L & S-R).",
         "Die 16 Schlitze zeigen immer nach OBEN! Die tiefere Rinne von Q1..Q4 liegt leicht links der Mitte."),
        ((0.68, 0.90, 0.80), "P01 bis P16 (16x Wellenschnitte, Brett 03, 04, 05):",
         "2-3 cm schmale Wellenstreifen mit je 5 Schlitzen auf der UNTERSEITE (fuer Q1..Q5).",
         "Flaches Ende = VORNE (bei Q1)  |  Steiles/hohes Ende = HINTEN (bei Q5, Kueste)."),
    ]
    for i, (col_box, t_bold, l1, l2) in enumerate(rules):
        ry = by + box_h - 33 - i * 33
        c.fill_rgb(*col_box)
        c.stroke_rgb(0.3, 0.35, 0.4)
        c.line_width(0.6)
        c.rect(bx + 12, ry - 12, 12, 20, fill=True, stroke=True)
        c.text(bx + 29, ry + 1, t_bold, size=7.8, bold=True, color=(0.10, 0.14, 0.20))
        c.text(bx + 29, ry - 8, l1, size=7.1, color=(0.20, 0.24, 0.30))
        c.text(bx + 29, ry - 17, l2, size=7.1, bold=True, color=(0.12, 0.30, 0.52))


# ---------------------------------------------------------------------------
# PAGE 2: LEGO STEPS 2, 3, 4, 5 (Grundrahmen & Mittel-Anker P08/P09)
# ---------------------------------------------------------------------------
def build_page2(c, d3):
    draw_header(
        c, 2,
        "SCHRITT 2 BIS 5: Erst S-L in B stecken, Q1..Q5 einhaengen, S-R schliessen und Mittel-Anker P08 & P09 setzen!"
    )
    parts = {p["id"]: p for p in d3["parts"]}

    # 2x2 grid of LEGO step panels
    col_x = [20, 426]
    row_y = [282, 16]
    pw, ph = 396, 256

    # ---- PANEL 2: B + S-L ----
    bx, by = col_x[0], row_y[0]
    c.fill_rgb(0.97, 0.98, 0.99)
    c.stroke_rgb(0.76, 0.80, 0.86)
    c.line_width(0.9)
    c.rect(bx, by, pw, ph, fill=True, stroke=True)

    c.step_badge(bx + 18, by + ph - 18, "2", bg=(0.10, 0.36, 0.68), r=12)
    c.text(bx + 36, by + ph - 16, "Bodenplatte B hinlegen & linke Wand S-L einstecken",
           size=10.2, bold=True, color=(0.10, 0.15, 0.24))
    c.text(bx + 36, by + ph - 28, "S-R jetzt noch NICHT einstecken (kommt erst in Schritt 4)!",
           size=8.0, bold=True, color=(0.78, 0.15, 0.12))

    # LEGO Parts Callout Box
    c.fill_rgb(1, 1, 1)
    c.stroke_rgb(0.72, 0.78, 0.86)
    c.line_width(0.8)
    c.rect(bx + 10, by + ph - 122, 115, 86, fill=True, stroke=True)
    c.fill_rgb(0.90, 0.93, 0.98)
    c.rect(bx + 10, by + ph - 50, 115, 14, fill=True, stroke=False)
    c.text(bx + 16, by + ph - 46, "Teile fuer Schritt 2:", size=7.5, bold=True, color=(0.12, 0.24, 0.45))
    draw_mini_part(c, parts["B"]["exterior"], bx + 15, by + ph - 85, 36, 30, (0.90, 0.82, 0.66), (0.48, 0.38, 0.22))
    c.text(bx + 56, by + ph - 68, "1x B", size=8.5, bold=True, color=(0.1, 0.1, 0.12))
    c.text(bx + 56, by + ph - 78, "(aus Brett 01)", size=7.0, color=(0.3, 0.35, 0.4))
    draw_mini_part(c, parts["S-L"]["exterior"], bx + 15, by + ph - 118, 36, 28, (0.20, 0.48, 0.80), (0.08, 0.25, 0.48))
    c.text(bx + 56, by + ph - 102, "1x S-L", size=8.5, bold=True, color=(0.08, 0.25, 0.48))
    c.text(bx + 56, by + ph - 112, "(aus Brett 01)", size=7.0, color=(0.3, 0.35, 0.4))

    # Instructions bottom-left
    c.text(bx + 10, by + 40, "1. B flach auf den Tisch legen.", size=7.8, bold=True, color=(0.15, 0.18, 0.22))
    c.text(bx + 10, by + 28, "2. S-L mit den 3 unteren Zapfen in", size=7.8, color=(0.15, 0.18, 0.22))
    c.text(bx + 10, by + 17, "   die 3 LINKEN Schlitze von B druecken.", size=7.8, color=(0.15, 0.18, 0.22))
    c.text(bx + 10, by + 6, "   Flaches Ende = vorne, hohes = hinten.", size=7.5, bold=True, color=(0.10, 0.36, 0.68))

    # 3D illustration for Step 2
    ox2, oy2, sc2 = bx + 178, by + 44, 0.37
    draw_assembly_3d(c, parts, ox2, oy2, sc2, existing_ids=[], active_ids=["B", "S-L"], lift_z={"S-L": 24.0})
    for f in (0.15, 0.5, 0.85):
        yc = f * 280.6
        p_top = iso_pt(0, yc, 22, ox2, oy2, sc2)
        p_bot = iso_pt(0, yc, 3, ox2, oy2, sc2)
        c.arrow(p_top[0], p_top[1], p_bot[0], p_bot[1], head=4.5)
    c.text(bx + 195, by + 170, "S-L (Links)", size=8.5, bold=True, color=(0.08, 0.25, 0.48))
    c.text(bx + 290, by + 18, "B (Bodenplatte)", size=8.0, bold=True, color=(0.48, 0.38, 0.22))

    # ---- PANEL 3: Hang Q5..Q1 into S-L ----
    bx, by = col_x[1], row_y[0]
    c.fill_rgb(0.97, 0.98, 0.99)
    c.stroke_rgb(0.76, 0.80, 0.86)
    c.line_width(0.9)
    c.rect(bx, by, pw, ph, fill=True, stroke=True)

    c.step_badge(bx + 18, by + ph - 18, "3", bg=(0.10, 0.36, 0.68), r=12)
    c.text(bx + 36, by + ph - 16, "Querbaender Q5 bis Q1 links in S-L einstecken",
           size=10.2, bold=True, color=(0.10, 0.15, 0.24))
    c.text(bx + 36, by + ph - 28, "Alle 16 Schlitze von Q1..Q5 zeigen nach OBEN!",
           size=8.0, bold=True, color=(0.75, 0.30, 0.05))

    # Parts Callout Box
    c.fill_rgb(1, 1, 1)
    c.stroke_rgb(0.72, 0.78, 0.86)
    c.line_width(0.8)
    c.rect(bx + 10, by + ph - 142, 122, 106, fill=True, stroke=True)
    c.fill_rgb(0.90, 0.93, 0.98)
    c.rect(bx + 10, by + ph - 50, 122, 14, fill=True, stroke=False)
    c.text(bx + 16, by + ph - 46, "Teile fuer Schritt 3:", size=7.5, bold=True, color=(0.12, 0.24, 0.45))
    q_list = [
        ("1x Q5", "Brett 03", "Loch 5 (hinten)"),
        ("1x Q4", "Brett 02", "Loch 4"),
        ("1x Q3", "Brett 02", "Loch 3 (Mitte)"),
        ("1x Q2", "Brett 02", "Loch 2"),
        ("1x Q1", "Brett 02", "Loch 1 (vorne)"),
    ]
    for qi, (qn, qbr, qloc) in enumerate(q_list):
        yy = by + ph - 64 - qi * 17
        c.fill_rgb(0.95, 0.50, 0.18)
        c.rect(bx + 15, yy - 2, 14, 7, fill=True, stroke=False)
        c.text(bx + 33, yy, f"{qn} ({qbr})", size=7.3, bold=True, color=(0.68, 0.25, 0.05))
        c.text(bx + 86, yy, qloc, size=6.6, color=(0.25, 0.30, 0.35))

    c.text(bx + 10, by + 38, "1. Den LINKEN Endzapfen von Q5..Q1", size=7.6, bold=True, color=(0.15, 0.18, 0.22))
    c.text(bx + 10, by + 27, "   in die 5 Rechteckloecher von S-L stecken.", size=7.6, color=(0.15, 0.18, 0.22))
    c.text(bx + 10, by + 16, "2. Achtung: Die tiefere Kurve von Q1..Q4", size=7.6, color=(0.15, 0.18, 0.22))
    c.text(bx + 10, by + 5, "   liegt leicht LINKS der Mitte (Schlitz 8)!", size=7.5, bold=True, color=(0.75, 0.30, 0.05))

    ox3, oy3, sc3 = bx + 180, by + 44, 0.37
    draw_assembly_3d(
        c, parts, ox3, oy3, sc3,
        existing_ids=["B", "S-L"],
        active_ids=["Q1", "Q2", "Q3", "Q4", "Q5"],
        show_q_labels=True
    )
    # Arrows showing Q bands plugging left into S-L
    for yc, zc in [(21.9, 80), (95.2, 130), (264.8, 258)]:
        p1 = iso_pt(45, yc, zc, ox3, oy3, sc3)
        p2 = iso_pt(5, yc, zc, ox3, oy3, sc3)
        c.arrow(p1[0], p1[1], p2[0], p2[1], head=4.5)

    # ---- PANEL 4: Close Right Wall S-R ----
    bx, by = col_x[0], row_y[1]
    c.fill_rgb(0.97, 0.98, 0.99)
    c.stroke_rgb(0.76, 0.80, 0.86)
    c.line_width(0.9)
    c.rect(bx, by, pw, ph, fill=True, stroke=True)

    c.step_badge(bx + 18, by + ph - 18, "4", bg=(0.10, 0.36, 0.68), r=12)
    c.text(bx + 36, by + ph - 16, "Rechte Seitenwand S-R auf Q1..Q5 faedeln & in B rasten",
           size=10.2, bold=True, color=(0.10, 0.15, 0.24))
    c.text(bx + 36, by + ph - 28, "Erst die 5 Zapfen von Q1..Q5 einfaedeln (1.), dann unten in B druecken (2.)!",
           size=7.8, bold=True, color=(0.10, 0.36, 0.68))

    # Parts Callout Box
    c.fill_rgb(1, 1, 1)
    c.stroke_rgb(0.72, 0.78, 0.86)
    c.line_width(0.8)
    c.rect(bx + 10, by + ph - 100, 118, 64, fill=True, stroke=True)
    c.fill_rgb(0.90, 0.93, 0.98)
    c.rect(bx + 10, by + ph - 50, 118, 14, fill=True, stroke=False)
    c.text(bx + 16, by + ph - 46, "Teile fuer Schritt 4:", size=7.5, bold=True, color=(0.12, 0.24, 0.45))
    draw_mini_part(c, parts["S-R"]["exterior"], bx + 15, by + ph - 94, 38, 36, (0.20, 0.48, 0.80), (0.08, 0.25, 0.48))
    c.text(bx + 58, by + ph - 72, "1x S-R", size=8.5, bold=True, color=(0.08, 0.25, 0.48))
    c.text(bx + 58, by + ph - 83, "(aus Brett 02)", size=7.0, color=(0.3, 0.35, 0.4))

    c.text(bx + 10, by + 40, "1. S-R rechts ansetzen und die 5 rechten", size=7.6, bold=True, color=(0.15, 0.18, 0.22))
    c.text(bx + 10, by + 29, "   Endzapfen von Q5..Q1 in S-R faedeln.", size=7.6, color=(0.15, 0.18, 0.22))
    c.text(bx + 10, by + 18, "2. Die 3 unteren Zapfen von S-R in die", size=7.6, bold=True, color=(0.15, 0.18, 0.22))
    c.text(bx + 10, by + 7, "   3 RECHTEN Schlitze von B druecken.", size=7.6, color=(0.15, 0.18, 0.22))

    ox4, oy4, sc4 = bx + 178, by + 44, 0.37
    draw_assembly_3d(
        c, parts, ox4, oy4, sc4,
        existing_ids=["B", "S-L", "Q1", "Q2", "Q3", "Q4", "Q5"],
        active_ids=["S-R"],
        lift_z={"S-R": 12.0}
    )
    # Arrows down into B
    for f in (0.15, 0.5, 0.85):
        yc = f * 280.6
        p_top = iso_pt(300, yc, 14, ox4, oy4, sc4)
        p_bot = iso_pt(300, yc, 0, ox4, oy4, sc4)
        c.arrow(p_top[0], p_top[1], p_bot[0], p_bot[1], head=4.5)
    c.text(bx + 305, by + 95, "S-R (Rechts)", size=8.5, bold=True, color=(0.08, 0.25, 0.48))

    # ---- PANEL 5: Center Anchor P08 & P09 ----
    bx, by = col_x[1], row_y[1]
    c.fill_rgb(0.97, 0.98, 0.99)
    c.stroke_rgb(0.76, 0.80, 0.86)
    c.line_width(0.9)
    c.rect(bx, by, pw, ph, fill=True, stroke=True)

    c.step_badge(bx + 18, by + ph - 18, "5", bg=(0.08, 0.52, 0.38), r=12)
    c.text(bx + 36, by + ph - 16, "PROFI-TRICK: Zuerst Mittel-Streifen P08 & P09 stecken!",
           size=10.2, bold=True, color=(0.06, 0.38, 0.28))
    c.text(bx + 36, by + ph - 28, "Stuetzt Q1..Q5 genau in der Mitte ab -> das ganze Gitter wird sofort starr!",
           size=7.8, bold=True, color=(0.15, 0.20, 0.28))

    # Parts Callout Box
    c.fill_rgb(1, 1, 1)
    c.stroke_rgb(0.72, 0.78, 0.86)
    c.line_width(0.8)
    c.rect(bx + 10, by + ph - 122, 125, 86, fill=True, stroke=True)
    c.fill_rgb(0.88, 0.96, 0.92)
    c.rect(bx + 10, by + ph - 50, 125, 14, fill=True, stroke=False)
    c.text(bx + 16, by + ph - 46, "Teile fuer Schritt 5:", size=7.5, bold=True, color=(0.06, 0.38, 0.28))
    draw_mini_part(c, parts["P08"]["exterior"], bx + 14, by + ph - 84, 38, 28, (0.18, 0.72, 0.54), (0.06, 0.42, 0.30))
    c.text(bx + 56, by + ph - 67, "1x P08 -> Schlitz 8", size=7.6, bold=True, color=(0.06, 0.38, 0.28))
    c.text(bx + 56, by + ph - 77, "(aus Brett 04)", size=6.8, color=(0.3, 0.35, 0.4))
    draw_mini_part(c, parts["P09"]["exterior"], bx + 14, by + ph - 118, 38, 28, (0.18, 0.72, 0.54), (0.06, 0.42, 0.30))
    c.text(bx + 56, by + ph - 101, "1x P09 -> Schlitz 9", size=7.6, bold=True, color=(0.06, 0.38, 0.28))
    c.text(bx + 56, by + ph - 111, "(aus Brett 04)", size=6.8, color=(0.3, 0.35, 0.4))

    c.text(bx + 10, by + 40, "1. Von links an Q1..Q5 abzaehlen:", size=7.6, bold=True, color=(0.15, 0.18, 0.22))
    c.text(bx + 10, by + 29, "   P08 in den 8. Schlitz, P09 in den 9. Schlitz", size=7.6, color=(0.15, 0.18, 0.22))
    c.text(bx + 10, by + 18, "   senkrecht von OBEN einschieben.", size=7.6, color=(0.15, 0.18, 0.22))
    c.text(bx + 10, by + 7, "2. Beide Oberkanten schliessen buendig ab.", size=7.6, bold=True, color=(0.06, 0.38, 0.28))

    ox5, oy5, sc5 = bx + 178, by + 44, 0.37
    draw_assembly_3d(
        c, parts, ox5, oy5, sc5,
        existing_ids=["B", "S-L", "S-R", "Q1", "Q2", "Q3", "Q4", "Q5"],
        active_ids=["P08", "P09"],
        lift_z={"P08": 18.0, "P09": 18.0},
        show_p_labels=("P08", "P09")
    )
    for y_arr in (60, 170, 260):
        z_top = max(v for u, v in parts["P08"]["exterior"] if abs(u - y_arr) < 5)
        p1 = iso_pt(149, y_arr, z_top + 48, ox5, oy5, sc5)
        p2 = iso_pt(149, y_arr, z_top + 24, ox5, oy5, sc5)
        c.arrow(p1[0], p1[1], p2[0], p2[1], head=4.5)


# ---------------------------------------------------------------------------
# PAGE 3: LEGO STEPS 6, 7, 8 + Master Slot Ruler 1..16
# ---------------------------------------------------------------------------
def build_page3(c, d3):
    draw_header(
        c, 3,
        "SCHRITT 6 BIS 8: Linke Haelfte (P01..P07) & rechte Haelfte (P10..P16) von oben einkaemmen, LEDs einsetzen!"
    )
    parts = {p["id"]: p for p in d3["parts"]}

    col_x = [20, 426]
    row_y = [282, 16]
    pw, ph = 396, 256

    # ---- PANEL 6: Left Half P01..P07 ----
    bx, by = col_x[0], row_y[0]
    c.fill_rgb(0.97, 0.98, 0.99)
    c.stroke_rgb(0.76, 0.80, 0.86)
    c.line_width(0.9)
    c.rect(bx, by, pw, ph, fill=True, stroke=True)

    c.step_badge(bx + 18, by + ph - 18, "6", bg=(0.08, 0.52, 0.38), r=12)
    c.text(bx + 36, by + ph - 16, "Linke Haelfte fuellen: P01 bis P07 (Schlitz 1 bis 7)",
           size=10.2, bold=True, color=(0.06, 0.38, 0.28))
    c.text(bx + 36, by + ph - 28, "Von links (P01 direkt neben S-L) nach rechts bis P07 (neben P08) von oben einstecken.",
           size=7.6, color=(0.20, 0.24, 0.30))

    # Parts Callout Box
    c.fill_rgb(1, 1, 1)
    c.stroke_rgb(0.72, 0.78, 0.86)
    c.line_width(0.8)
    c.rect(bx + 10, by + ph - 156, 130, 120, fill=True, stroke=True)
    c.fill_rgb(0.88, 0.96, 0.92)
    c.rect(bx + 10, by + ph - 50, 130, 14, fill=True, stroke=False)
    c.text(bx + 15, by + ph - 46, "7 Teile fuer Schritt 6:", size=7.5, bold=True, color=(0.06, 0.38, 0.28))
    left_strips = [
        ("P01", "Brett 03", "Schlitz 1 (links)"),
        ("P02", "Brett 05", "Schlitz 2"),
        ("P03", "Brett 05", "Schlitz 3"),
        ("P04", "Brett 04", "Schlitz 4"),
        ("P05", "Brett 05", "Schlitz 5"),
        ("P06", "Brett 04", "Schlitz 6"),
        ("P07", "Brett 03", "Schlitz 7"),
    ]
    for si, (pid, pbr, psl) in enumerate(left_strips):
        yy = by + ph - 63 - si * 14.2
        c.fill_rgb(0.18, 0.72, 0.54)
        c.rect(bx + 14, yy - 1.5, 9, 6.5, fill=True, stroke=False)
        c.text(bx + 26, yy, f"{pid} ({pbr})", size=7.1, bold=True, color=(0.06, 0.38, 0.28))
        c.text(bx + 80, yy, f"-> {psl}", size=6.8, color=(0.20, 0.24, 0.30))

    c.text(bx + 10, by + 26, "Jeden Streifen mit den 5 unteren Schlitzen", size=7.5, color=(0.15, 0.18, 0.22))
    c.text(bx + 10, by + 15, "senkrecht von OBEN in Q1..Q5 druecken.", size=7.5, bold=True, color=(0.06, 0.38, 0.28))

    ox6, oy6, sc6 = bx + 180, by + 44, 0.37
    draw_assembly_3d(
        c, parts, ox6, oy6, sc6,
        existing_ids=["B", "S-L", "S-R", "Q1", "Q2", "Q3", "Q4", "Q5", "P08", "P09"],
        active_ids=["P01", "P02", "P03", "P04", "P05", "P06", "P07"],
        show_p_labels=("P01", "P04", "P07")
    )
    for xm in (18.5, 71.1, 123.7):
        p1 = iso_pt(xm, 200, 225, ox6, oy6, sc6)
        p2 = iso_pt(xm, 200, 198, ox6, oy6, sc6)
        c.arrow(p1[0], p1[1], p2[0], p2[1], head=4.2)

    # ---- PANEL 7: Right Half P10..P16 ----
    bx, by = col_x[1], row_y[0]
    c.fill_rgb(0.97, 0.98, 0.99)
    c.stroke_rgb(0.76, 0.80, 0.86)
    c.line_width(0.9)
    c.rect(bx, by, pw, ph, fill=True, stroke=True)

    c.step_badge(bx + 18, by + ph - 18, "7", bg=(0.08, 0.52, 0.38), r=12)
    c.text(bx + 36, by + ph - 16, "Rechte Haelfte fuellen: P10 bis P16 (Schlitz 10 bis 16)",
           size=10.2, bold=True, color=(0.06, 0.38, 0.28))
    c.text(bx + 36, by + ph - 28, "Von der Mitte (P10 neben P09) nach rechts bis P16 (direkt neben S-R) einstecken.",
           size=7.6, color=(0.20, 0.24, 0.30))

    # Parts Callout Box
    c.fill_rgb(1, 1, 1)
    c.stroke_rgb(0.72, 0.78, 0.86)
    c.line_width(0.8)
    c.rect(bx + 10, by + ph - 156, 130, 120, fill=True, stroke=True)
    c.fill_rgb(0.88, 0.96, 0.92)
    c.rect(bx + 10, by + ph - 50, 130, 14, fill=True, stroke=False)
    c.text(bx + 15, by + ph - 46, "7 Teile fuer Schritt 7:", size=7.5, bold=True, color=(0.06, 0.38, 0.28))
    right_strips = [
        ("P10", "Brett 03", "Schlitz 10"),
        ("P11", "Brett 05", "Schlitz 11"),
        ("P12", "Brett 05", "Schlitz 12"),
        ("P13", "Brett 04", "Schlitz 13"),
        ("P14", "Brett 03", "Schlitz 14"),
        ("P15", "Brett 03", "Schlitz 15"),
        ("P16", "Brett 05", "Schlitz 16 (rechts)"),
    ]
    for si, (pid, pbr, psl) in enumerate(right_strips):
        yy = by + ph - 63 - si * 14.2
        c.fill_rgb(0.18, 0.72, 0.54)
        c.rect(bx + 14, yy - 1.5, 9, 6.5, fill=True, stroke=False)
        c.text(bx + 26, yy, f"{pid} ({pbr})", size=7.1, bold=True, color=(0.06, 0.38, 0.28))
        c.text(bx + 80, yy, f"-> {psl}", size=6.8, color=(0.20, 0.24, 0.30))

    c.text(bx + 10, by + 26, "Alle 24 Holzteile sind jetzt fest", size=7.5, bold=True, color=(0.15, 0.18, 0.22))
    c.text(bx + 10, by + 15, "miteinander verzahnt (komplett ohne Leim!).", size=7.5, color=(0.15, 0.18, 0.22))

    ox7, oy7, sc7 = bx + 180, by + 44, 0.37
    draw_assembly_3d(
        c, parts, ox7, oy7, sc7,
        existing_ids=["B", "S-L", "S-R", "Q1", "Q2", "Q3", "Q4", "Q5"] + [f"P{k:02d}" for k in range(1, 10)],
        active_ids=[f"P{k:02d}" for k in range(10, 17)],
        show_p_labels=("P10", "P13", "P16")
    )
    for xm in (176.3, 228.9, 281.5):
        p1 = iso_pt(xm, 200, 225, ox7, oy7, sc7)
        p2 = iso_pt(xm, 200, 198, ox7, oy7, sc7)
        c.arrow(p1[0], p1[1], p2[0], p2[1], head=4.2)

    # ---- PANEL 8 (Bottom-Left): Front Comb Ruler (Schlitz 1..16 Lookup) ----
    bx, by = col_x[0], row_y[1]
    c.fill_rgb(0.97, 0.98, 0.99)
    c.stroke_rgb(0.76, 0.80, 0.86)
    c.line_width(0.9)
    c.rect(bx, by, pw, ph, fill=True, stroke=True)

    c.text(bx + 14, by + ph - 18,
           "KAMM-LINEAL (VORDERANSICHT AUF QUERBAND Q1..Q5: SCHLITZ 1 BIS 16)",
           size=9.5, bold=True, color=(0.10, 0.15, 0.24))
    c.text(bx + 14, by + ph - 30,
           "So sitzen alle 18 Scheiben im Abstand von 17,5 mm (lichte Luecke 15,5 mm fuer die LEDs) nebeneinander:",
           size=7.6, color=(0.25, 0.30, 0.36))

    # Draw comb bar across the panel
    bar_x = bx + 18
    bar_w = pw - 36
    bar_y = by + 95
    # Q band orange bar
    c.fill_rgb(0.95, 0.50, 0.18)
    c.stroke_rgb(0.68, 0.25, 0.05)
    c.line_width(0.9)
    c.rect(bar_x, bar_y, bar_w, 32, fill=True, stroke=True)

    all_slices = [
        ("S-L", "Br.01", "Wand L"),
        ("P01", "Br.03", "Schl.1"),
        ("P02", "Br.05", "Schl.2"),
        ("P03", "Br.05", "Schl.3"),
        ("P04", "Br.04", "Schl.4"),
        ("P05", "Br.05", "Schl.5"),
        ("P06", "Br.04", "Schl.6"),
        ("P07", "Br.03", "Schl.7"),
        ("P08", "Br.04", "Schl.8"),
        ("P09", "Br.04", "Schl.9"),
        ("P10", "Br.03", "Schl.10"),
        ("P11", "Br.05", "Schl.11"),
        ("P12", "Br.05", "Schl.12"),
        ("P13", "Br.04", "Schl.13"),
        ("P14", "Br.03", "Schl.14"),
        ("P15", "Br.03", "Schl.15"),
        ("P16", "Br.05", "Schl.16"),
        ("S-R", "Br.02", "Wand R"),
    ]
    step_x = bar_w / 17.0
    for idx_s, (sid, sbr, ssl) in enumerate(all_slices):
        sx = bar_x + idx_s * step_x
        is_side = sid in ("S-L", "S-R")
        is_mid = sid in ("P08", "P09")
        if is_side:
            c.fill_rgb(0.20, 0.48, 0.80)
            c.rect(sx - 2.5, bar_y - 30, 5.0, 96, fill=True, stroke=False)
        else:
            # White slot notch in Q band
            c.fill_rgb(1, 1, 1)
            c.rect(sx - 2.2, bar_y + 16, 4.4, 17, fill=True, stroke=False)
            # Green strip sitting in slot
            c.fill_rgb(0.08, 0.52, 0.38) if is_mid else c.fill_rgb(0.22, 0.74, 0.56)
            c.rect(sx - 2.0, bar_y + 16, 4.0, 48, fill=True, stroke=False)

        # Label above strip
        c.text(sx, bar_y + 69 + (idx_s % 2) * 10, sid, size=6.8, bold=True,
               color=(0.08, 0.25, 0.48) if is_side else ((0.80, 0.12, 0.12) if is_mid else (0.06, 0.38, 0.28)),
               align="center")
        # Board number below Q band
        c.text(sx, bar_y - 12 - (idx_s % 2) * 9, sbr, size=6.0, bold=True, color=(0.25, 0.30, 0.38), align="center")
        if not is_side:
            c.text(sx, bar_y + 5, str(idx_s), size=6.5, bold=True, color=(1, 1, 1), align="center")

    c.text(bx + 14, by + 40,
           "Obere Zeile = Bauteil-ID (S-L, P01..P16, S-R)  |  Zahl im orangen Balken = Schlitz-Nr. (1 bis 16)",
           size=7.4, bold=True, color=(0.15, 0.18, 0.22))
    c.text(bx + 14, by + 28,
           "Untere Zeile = Aus welchem Laser-Brett (Br.01 bis Br.05) das Teil stammt.",
           size=7.4, color=(0.25, 0.30, 0.36))
    c.text(bx + 14, by + 14,
           "Rot markiert (P08, P09 in Schlitz 8 & 9): Zuerst in Schritt 5 als Mittel-Anker einstecken!",
           size=7.4, bold=True, color=(0.80, 0.12, 0.12))

    # ---- PANEL 9 (Bottom-Right): STEP 8 LED Wiring from Behind ----
    bx, by = col_x[1], row_y[1]
    c.fill_rgb(0.97, 0.98, 0.99)
    c.stroke_rgb(0.76, 0.80, 0.86)
    c.line_width(0.9)
    c.rect(bx, by, pw, ph, fill=True, stroke=True)

    c.step_badge(bx + 18, by + ph - 18, "8", bg=(0.82, 0.18, 0.15), r=12)
    c.text(bx + 36, by + ph - 16, "LED-Verkabelung von hinten durch den offenen Hohlraum",
           size=10.2, bold=True, color=(0.10, 0.15, 0.24))
    c.text(bx + 36, by + ph - 28, "24,5 cm freier Arbeitsraum unter den 2-3 cm kurzen Wellenschnitten!",
           size=7.8, bold=True, color=(0.82, 0.18, 0.15))

    # Draw side cross-section diagram of a strip + 5 cross bands + open back cavity + LEDs
    sx0, sy0 = bx + 18, by + 40
    sc_side = 0.56
    p06 = parts["P06"]["exterior"]
    p06_pts = [(sx0 + u * sc_side, sy0 + v * sc_side) for u, v in p06]
    # Floor B in side view
    c.fill_rgb(0.90, 0.82, 0.66)
    c.stroke_rgb(0.48, 0.38, 0.22)
    c.line_width(0.8)
    c.rect(sx0 - 2, sy0 - 5, 286 * sc_side, 5, fill=True, stroke=True)

    # Open cavity highlight under the wave strip
    c.fill_rgb(0.93, 0.97, 1.0)
    c.stroke_rgb(0.65, 0.78, 0.92)
    c.dash((3, 2), 0)
    c.poly([(sx0 + 10, sy0 + 2), (sx0 + 156, sy0 + 2), (sx0 + 156, sy0 + 130), (sx0 + 10, sy0 + 16)],
           close=True, fill=True, stroke=True)
    c.dash()
    c.text(sx0 + 114, sy0 + 44, "OFFENER FREIRAUM", size=7.6, bold=True, color=(0.12, 0.35, 0.65), align="center")
    c.text(sx0 + 114, sy0 + 33, "(bis 24,5 cm hoch)", size=7.0, bold=True, color=(0.12, 0.35, 0.65), align="center")
    c.text(sx0 + 114, sy0 + 22, "Von hinten greifen", size=6.8, color=(0.20, 0.30, 0.45), align="center")
    c.text(sx0 + 114, sy0 + 12, "& LEDs verkabeln!", size=6.8, color=(0.20, 0.30, 0.45), align="center")

    # Green profile strip P06
    c.fill_rgb(0.18, 0.72, 0.54)
    c.stroke_rgb(0.06, 0.42, 0.30)
    c.line_width(1.0)
    c.poly(p06_pts, close=True, fill=True, stroke=True)

    # Orange cross bands Q1..Q5 in side section
    for qid, yc in [("Q1", 21.9), ("Q2", 54.9), ("Q3", 95.2), ("Q4", 145.8), ("Q5", 264.8)]:
        z_at = max(v for u, v in p06 if abs(u - yc) < 2.0)
        qx = sx0 + yc * sc_side
        qy = sy0 + (z_at - 20) * sc_side
        c.fill_rgb(0.95, 0.50, 0.18)
        c.stroke_rgb(0.68, 0.25, 0.05)
        c.rect(qx - 2, qy, 4, 20 * sc_side, fill=True, stroke=True)
        c.text(qx, qy + 20 * sc_side + 4, qid, size=6.8, bold=True, color=(0.68, 0.25, 0.05), align="center")

    # Red LED dots along the slope between Q bands
    for u_led in (12, 38, 74, 120, 185, 230):
        z_at = max(v for u, v in p06 if abs(u - u_led) < 2.0)
        c.fill_rgb(0.90, 0.12, 0.12)
        c.circle(sx0 + u_led * sc_side, sy0 + (z_at - 6) * sc_side, 3.0, fill=True, stroke=False)

    # Instructions on right side of Panel 8
    tx8 = bx + 210
    c.text(tx8, by + ph - 52, "So werden die LEDs montiert:", size=8.5, bold=True, color=(0.10, 0.15, 0.24))
    led_steps = [
        "1. Zwischen den 18 Scheiben liegen",
        "   genau 17 Luecken (je 15,5 mm breit):",
        "   - Luecke 1: zwischen S-L und P01",
        "   - Luecke 2: zwischen P01 und P02",
        "   - ... bis Luecke 17: P16 und S-R.",
        "2. Die Wellenschnitte P01..P16 sind",
        "   nur 2-3 cm kurz -> von hinten",
        "   kommst du frei an jede Stelle.",
        "3. Die 5 Querbaender Q1..Q5 sitzen",
        "   exakt in LED-freien Fenstern,",
        "   keine LED wird verdeckt.",
        "4. Exakte X/Y/Z-Position jeder der",
        "   109 LEDs: siehe led_montage.csv.",
    ]
    for li, lstr in enumerate(led_steps):
        c.text(tx8, by + ph - 68 - li * 11.8, lstr, size=7.3,
               bold=lstr.startswith(("1.", "2.", "3.", "4.")),
               color=(0.15, 0.18, 0.22))


def build_pdf(pages, out_path):
    objs = []
    page_obj_nums = [5 + 2 * i for i in range(len(pages))]
    kids_str = " ".join(f"{n} 0 R" for n in page_obj_nums)

    objs.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    objs.append(f"2 0 obj\n<< /Type /Pages /Kids [{kids_str}] /Count {len(pages)} >>\nendobj\n".encode("ascii"))
    objs.append(
        b"3 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>\nendobj\n"
    )
    objs.append(
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>\nendobj\n"
    )

    for i, p in enumerate(pages):
        p_num = 5 + 2 * i
        c_num = p_num + 1
        comp = zlib.compress(p.stream_bytes(), 9)
        objs.append(
            f"{p_num} 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {W_PT:.2f} {H_PT:.2f}] "
            f"/Contents {c_num} 0 R /Resources << /ProcSet [/PDF /Text] "
            f"/Font << /F1 3 0 R /F2 4 0 R >> >> >>\nendobj\n".encode("ascii")
        )
        objs.append(
            f"{c_num} 0 obj\n<< /Filter /FlateDecode /Length {len(comp)} >>\nstream\n".encode("ascii")
            + comp
            + b"\nendstream\nendobj\n"
        )

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for ob in objs:
        offsets.append(len(out))
        out.extend(ob)
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for off in offsets:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("ascii")
    )
    out_path.write_bytes(out)


def main():
    d3 = json.loads((OUT / "teile_3d.json").read_text(encoding="utf-8"))
    metrics = json.loads((OUT / "metriken_laser.json").read_text(encoding="utf-8"))

    p1, p2, p3 = Canvas(), Canvas(), Canvas()
    build_page1(p1, d3, metrics)
    build_page2(p2, d3)
    build_page3(p3, d3)

    pdf1 = OUT / "zusammenbau_anleitung.pdf"
    build_pdf([p1, p2, p3], pdf1)
    print("Wrote", pdf1, pdf1.stat().st_size)

    if DELIV.exists():
        pdf2 = DELIV / "00_Zusammenbau_Anleitung.pdf"
        build_pdf([p1, p2, p3], pdf2)
        print("Wrote", pdf2, pdf2.stat().st_size)


if __name__ == "__main__":
    main()
