"""Generate a 4-page visual PDF guide with 3D model views for mounting and wiring the 8 horizontal LED strips (S1..S8 on Arduino Pin 2..9).

Usage:
  /usr/bin/python3 modell/led_reihen_pdf.py
Writes:
  modell/export/laser_v1/led_reihen_anleitung.pdf
  modell/export/laser_v1/斜面模型_切断用_600x300_20261112/00_LED_8_Reihen_Anleitung.pdf
"""
import json
import math
import pathlib
import shutil
import zlib

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "export" / "laser_v1"
DELIV = OUT / "斜面模型_切断用_600x300_20261112"
W_PT, H_PT = 841.89, 595.28  # A4 landscape


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

    def poly(self, pts, close=True, fill=False, stroke=True):
        if not pts:
            return
        segs = [f"{pts[0][0]:.2f} {pts[0][1]:.2f} m"]
        for x, y in pts[1:]:
            segs.append(f"{x:.2f} {y:.2f} l")
        if close:
            segs.append("h")
        op = "B" if (fill and stroke) else ("f" if fill else "S")
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

    def step_badge(self, cx, cy, num_str, bg=(0.10, 0.36, 0.68), r=10.5):
        self.fill_rgb(*bg)
        self.circle(cx, cy, r, fill=True, stroke=False)
        self.text(cx, cy - 3.8, num_str, size=11.0, bold=True, rgb=(1, 1, 1), align="center")

    def text(self, x, y, s, size=10, bold=False, rgb=(0.1, 0.1, 0.1), align="left"):
        font = "/F2" if bold else "/F1"
        w_est = len(s) * size * (0.55 if bold else 0.50)
        if align == "center":
            x -= w_est / 2.0
        elif align == "right":
            x -= w_est
        r, g, b = rgb
        esc = pdf_escape(s)
        self.ops.append(f"BT {font} {size:.2f} Tf {r:.3f} {g:.3f} {b:.3f} rg {x:.2f} {y:.2f} Td ({esc}) Tj ET")

    def stream_bytes(self):
        return "\n".join(self.ops).encode("ascii")


COLOR_MAP = {
    "rot": (0.90, 0.12, 0.12),
    "orange": (0.96, 0.45, 0.05),
    "gelb": (0.95, 0.78, 0.05),
    "blau": (0.16, 0.48, 0.92),
}


def interp_curve(pts, y):
    for (u0, z0), (u1, z1) in zip(pts, pts[1:]):
        if u0 <= y <= u1:
            return z0 if u1 == u0 else z0 + (y - u0) / (u1 - u0) * (z1 - z0)
    return pts[-1][1] if y >= pts[-1][0] else pts[0][1]


def iso_pt(x, y, z, ox, oy, sc, ang_x_deg=24.0, ang_y_deg=32.0):
    a = math.radians(ang_x_deg)
    b = math.radians(ang_y_deg)
    px = ox + sc * (x * math.cos(a) + y * math.cos(b))
    py = oy + sc * (-x * math.sin(a) + y * math.sin(b) + z)
    return px, py


def interp_surface_z(top_curves, x_mm, y_mm):
    """Interpolate the 3D surface Z height across the 18 plates (S-L, P01..P16, S-R) at any (x_mm, y_mm)."""
    plate_xs = [("S-L", 1.0)] + [(f"P{k:02d}", 1.0 + k * (298.0 / 17.0)) for k in range(1, 17)] + [("S-R", 299.0)]
    if x_mm <= plate_xs[0][1]:
        return interp_curve(top_curves["S-L"], y_mm)
    if x_mm >= plate_xs[-1][1]:
        return interp_curve(top_curves["S-R"], y_mm)
    for (id0, x0), (id1, x1) in zip(plate_xs, plate_xs[1:]):
        if x0 <= x_mm <= x1:
            t = (x_mm - x0) / max(1e-6, x1 - x0)
            z0 = interp_curve(top_curves[id0], y_mm)
            z1 = interp_curve(top_curves[id1], y_mm)
            return z0 + t * (z1 - z0)
    return interp_curve(top_curves["P08"], y_mm)


def draw_page1_3d_visual(c, lr, d3, top_curves):
    """Page 1: Large 3D Isometric View of the Full 16-Rail Model + 3D Close-Up of how the 8 LED rows attach underneath."""
    c.fill_rgb(0.98, 0.98, 0.99)
    c.rect(0, 0, W_PT, H_PT, fill=True, stroke=False)

    # Header bar
    c.fill_rgb(0.11, 0.18, 0.30)
    c.rect(0, H_PT - 48, W_PT, 48, fill=True, stroke=False)
    c.text(24, H_PT - 26, "SEITE 1/4: 3D-ANSICHT DES HANGMODELLS & EINBAU-ORT DER 8 LED-REIHEN (S1..S8)", size=13.5, bold=True, rgb=(1, 1, 1))
    c.text(24, H_PT - 41, "Visuelle 3D-Darstellung: Wo die 8 LED-Streifen (Pin 2..9) im 16-Schienen-Modell sitzen und wie sie von unten angebunden werden", size=9.2, rgb=(0.82, 0.90, 1.0))

    # Left card: Full 3D Isometric Model with the 8 LED strips S1..S8
    c.fill_rgb(1, 1, 1)
    c.stroke_rgb(0.80, 0.84, 0.88)
    c.line_width(1.0)
    c.rect(18, 20, 472, 515, fill=True, stroke=True)

    c.text(28, 518, "1. 3D-Gesamtansicht: Das 16-Schienen-Modell (P01..P16) mit den 8 LED-Reihen S1..S8", size=10.2, bold=True, rgb=(0.11, 0.18, 0.30))
    c.text(28, 504, "Grün = 16 Wellen-Schienen P01..P16 | Orange = 5 Querbänder Q1..Q5 | Schwarz/Bunt = 8 LED-Streifen S1..S8 von unten an P01..P16", size=7.5, rgb=(0.3, 0.33, 0.38))

    parts = {p["id"]: p for p in d3["parts"]}
    ox, oy, sc = 78.0, 152.0, 0.68

    # 1. Floor B in 3D
    pts_b = [iso_pt(u, v, 0.0, ox, oy, sc) for u, v in parts["B"]["exterior"]]
    c.fill_rgb(0.92, 0.88, 0.78)
    c.stroke_rgb(0.62, 0.55, 0.42)
    c.line_width(0.8)
    c.poly(pts_b, close=True, fill=True, stroke=True)

    # 2. Left side wall S-L
    pts_sl = [iso_pt(0.0, u, v, ox, oy, sc) for u, v in parts["S-L"]["exterior"]]
    c.fill_rgb(0.75, 0.85, 0.96)
    c.stroke_rgb(0.20, 0.45, 0.75)
    c.line_width(0.8)
    c.poly(pts_sl, close=True, fill=True, stroke=True)
    tx_sl, ty_sl = iso_pt(0.0, 15.0, 25.0, ox, oy, sc)
    c.text(tx_sl - 18, ty_sl, "S-L (Links)", size=7.2, bold=True, rgb=(0.12, 0.35, 0.68), align="right")

    # 3. Crossbars Q5..Q1 (back to front)
    q_label_ys = {5: 400.0, 4: 310.0, 3: 245.0, 2: 195.0, 1: 150.0}
    for j in range(5, 0, -1):
        qid = f"Q{j}"
        qp = parts[qid]
        yc = qp["place"]["at"] + 1.0
        pts_q = [iso_pt(u, yc, v, ox, oy, sc) for u, v in qp["exterior"]]
        c.fill_rgb(0.96, 0.68, 0.36)
        c.stroke_rgb(0.75, 0.35, 0.05)
        c.line_width(0.75)
        c.poly(pts_q, close=True, fill=True, stroke=True)
        # Leader line to clean right margin for Q1..Q5
        top_qz = qp["exterior"][-1][1]
        qx_r, qy_r = iso_pt(300.0, yc, top_qz * 0.6, ox, oy, sc)
        ly_targ = q_label_ys[j]
        c.stroke_rgb(0.75, 0.35, 0.05)
        c.line_width(0.8)
        c.line(qx_r, qy_r, 424.0, ly_targ + 3.0)
        c.fill_rgb(0.99, 0.94, 0.86)
        c.rect(424.0, ly_targ - 4.0, 58.0, 14.0, fill=True, stroke=True)
        c.text(427.0, ly_targ, f"{qid} (y={yc:.0f}mm)", size=6.2, bold=True, rgb=(0.68, 0.25, 0.02))

    # 4. Wave rails P01..P16 (left to right)
    for k in range(1, 17):
        pid = f"P{k:02d}"
        pp = parts[pid]
        xm = pp["place"]["at"] + 1.0
        pts_p = [iso_pt(xm, u, v, ox, oy, sc) for u, v in pp["exterior"]]
        c.fill_rgb(0.55, 0.84, 0.70)
        c.stroke_rgb(0.12, 0.50, 0.34)
        c.line_width(0.55)
        c.poly(pts_p, close=True, fill=True, stroke=True)
        if k in (1, 4, 8, 12, 16):
            top_z = max(v for u, v in pp["exterior"] if u > 274)
            px_t, py_t = iso_pt(xm, 280.6, top_z + 8.0, ox, oy, sc)
            c.text(px_t, py_t, pid, size=6.2, bold=True, rgb=(0.06, 0.42, 0.28), align="center")

    # 5. Draw the 8 LED rows S1..S8 in 3D across the 16 rails!
    active_map = {(s["strang"], s["luecke"]): s for s in lr["sharks"]}
    sample_xs = [k * 15.0 for k in range(21)]  # 0 to 300 mm

    for idx, r in enumerate(lr["rows"]):
        sid = r["strang"]
        yc = r["y_mm"]

        # Draw the 3D clip carrier band at z_clip = z_surface - 20 mm (underneath the 20 mm rails)
        clip_top_pts = []
        clip_bot_pts = []
        for x_mm in sample_xs:
            z_surf = interp_surface_z(top_curves, x_mm, yc)
            z_clip = max(2.0, z_surf - 20.0)
            clip_top_pts.append(iso_pt(x_mm, yc, z_clip + 2.5, ox, oy, sc))
            clip_bot_pts.append(iso_pt(x_mm, yc, z_clip - 3.5, ox, oy, sc))
        c.fill_rgb(0.18, 0.20, 0.24)
        c.stroke_rgb(0.05, 0.05, 0.08)
        c.line_width(0.6)
        c.poly(clip_top_pts + list(reversed(clip_bot_pts)), close=True, fill=True, stroke=True)

        # Draw glowing band on the top surface (where light hits the paper layer)
        surf_front = [iso_pt(x_mm, yc - 3.2, interp_surface_z(top_curves, x_mm, yc), ox, oy, sc) for x_mm in sample_xs]
        surf_back = [iso_pt(x_mm, yc + 3.2, interp_surface_z(top_curves, x_mm, yc), ox, oy, sc) for x_mm in reversed(sample_xs)]
        c.fill_rgb(0.22, 0.25, 0.30)
        c.stroke_rgb(0.95, 0.75, 0.20)
        c.line_width(0.7)
        c.poly(surf_front + surf_back, close=True, fill=True, stroke=True)

        # Draw the 17 LED positions in the 17 gaps on the 3D surface
        for g in range(1, 18):
            gx_mm = 1.0 + (g - 0.5) * (298.0 / 17.0)
            gz_mm = interp_surface_z(top_curves, gx_mm, yc)
            lx_pt, ly_pt = iso_pt(gx_mm, yc, gz_mm + 1.0, ox, oy, sc)
            shark = active_map.get((sid, g))
            if shark:
                cr, cg, cb = COLOR_MAP[shark["farbe"]]
                c.fill_rgb(cr, cg, cb)
                c.stroke_rgb(1, 1, 1)
                c.line_width(0.45)
                c.circle(lx_pt, ly_pt, 2.5, fill=True, stroke=True)
            else:
                c.fill_rgb(0.40, 0.42, 0.46)
                c.circle(lx_pt, ly_pt, 1.2, fill=True, stroke=False)

        # Left cable feed at x = 0 mm (S-L) with callout badge for S1..S8
        z_left = interp_surface_z(top_curves, 1.0, yc)
        p_in_x, p_in_y = iso_pt(0.0, yc, z_left, ox, oy, sc)
        # Stagger labels cleanly on the left
        lbl_x = 24.0
        lbl_y = 468.0 - idx * 38.0
        c.stroke_rgb(0.82, 0.22, 0.08)
        c.line_width(1.0)
        c.line(lbl_x + 56.0, lbl_y + 4.0, p_in_x, p_in_y)
        c.fill_rgb(0.82, 0.22, 0.08)
        c.circle(p_in_x, p_in_y, 2.2, fill=True, stroke=False)

        c.fill_rgb(0.14, 0.22, 0.36)
        c.stroke_rgb(0.82, 0.22, 0.08)
        c.line_width(0.8)
        c.rect(lbl_x, lbl_y - 6.0, 56.0, 21.0, fill=True, stroke=True)
        c.text(lbl_x + 2.5, lbl_y + 6.0, f"{sid} (Pin {r['arduino_pin']})", size=6.3, bold=True, rgb=(1, 1, 1))
        q_dist_str = f"{264.8 - yc:.0f}mm v.Q5" if idx < 6 else ("21mm v.Q4" if sid == "S7" else "13mm v.Q2")
        c.text(lbl_x + 2.5, lbl_y - 3.0, f"y={yc:.0f} ({q_dist_str})", size=5.2, rgb=(0.98, 0.85, 0.45))

    # 6. Right side wall S-R as dashed transparent outline so rails & strips stay visible
    pts_sr = [iso_pt(300.0, u, v, ox, oy, sc) for u, v in parts["S-R"]["exterior"]]
    c.stroke_rgb(0.20, 0.45, 0.75)
    c.line_width(1.0)
    c.dash((3, 2), 0)
    c.poly(pts_sr, close=True, fill=False, stroke=True)
    c.dash((), 0)
    tx_sr, ty_sr = iso_pt(300.0, 40.0, 10.0, ox, oy, sc)
    c.text(tx_sr - 10, ty_sr - 14, "S-R (Rechts, x=300 mm)", size=6.8, bold=True, rgb=(0.12, 0.35, 0.68))

    # Orientation arrows at bottom of 3D view
    c.fill_rgb(0.95, 0.97, 1.0)
    c.stroke_rgb(0.75, 0.82, 0.90)
    c.rect(28, 28, 452, 82, fill=True, stroke=True)
    c.text(36, 96, "Orientierung im 3D-Modell (Wo wird welche Reihe angebunden?):", size=8.4, bold=True, rgb=(0.11, 0.18, 0.30))
    c.text(36, 82, "- Oben am Hang (Küsten-Feld zwischen Q4 und Q5, y = 161..248 mm): Hier sitzen dicht hintereinander S1, S2, S3, S4, S5 und S6", size=7.2, bold=True, rgb=(0.15, 0.20, 0.28))
    c.text(36, 70, "  im festen Abstand von 17 mm, 34 mm, 51 mm, 68 mm, 86 mm und 104 mm vor Querband Q5 (y = 264,8 mm).", size=7.1, rgb=(0.25, 0.28, 0.32))
    c.text(36, 56, "- Mittlerer Hang (Feld zwischen Q3 und Q4): Hier sitzt Reihe S7 (Pin 8) bei y = 125 mm (genau 21 mm vor Querband Q4).", size=7.2, bold=True, rgb=(0.15, 0.20, 0.28))
    c.text(36, 44, "- Unterer Hang / Tiefsee (Feld zwischen Q1 und Q2): Hier sitzt Reihe S8 (Pin 9) bei y = 42 mm (genau 13 mm vor Querband Q2).", size=7.2, bold=True, rgb=(0.15, 0.20, 0.28))
    c.text(36, 32, "- Alle 8 Kabel-Anfänge (5V/Din/GND) kommen LINKS bei Seitenwand S-L heraus und gehen direkt an Arduino Pin 2 bis Pin 9!", size=7.2, bold=True, rgb=(0.78, 0.18, 0.05))

    # Right card: 3D Close-Up View of Mounting from Underneath + Step-by-Step Visual Guide
    c.fill_rgb(1, 1, 1)
    c.stroke_rgb(0.80, 0.84, 0.88)
    c.line_width(1.0)
    c.rect(498, 20, 326, 515, fill=True, stroke=True)

    c.text(508, 518, "2. 3D-Detailansicht: So klemmt ihr jede LED-Reihe an P01..P16", size=10.0, bold=True, rgb=(0.11, 0.18, 0.30))
    c.text(508, 504, "Jede Reihe S1..S8 wird von UNTEN an die 20 mm Schienen P01..P16 geklipst/angebunden.", size=7.5, rgb=(0.3, 0.33, 0.38))

    # Draw a 3D close-up isometric diagram of 4 rails (S-L, P01, P02, P03) and two LED rows (one mounted, one sliding up from below)
    ox2, oy2, sc2 = 542.0, 290.0, 2.05

    def iso_detail(x, y, z):
        return iso_pt(x, y, z, ox2, oy2, sc2, ang_x_deg=22.0, ang_y_deg=28.0)

    # Draw 4 rails in 3D close-up: S-L (x=0), P01 (x=18.5), P02 (x=36.0), P03 (x=53.6), P04 (x=71.1)
    rail_infos = [("S-L", 0.0, (0.68, 0.82, 0.96), (0.18, 0.42, 0.72)),
                  ("P01", 18.5, (0.62, 0.88, 0.74), (0.10, 0.48, 0.30)),
                  ("P02", 36.0, (0.62, 0.88, 0.74), (0.10, 0.48, 0.30)),
                  ("P03", 53.6, (0.62, 0.88, 0.74), (0.10, 0.48, 0.30)),
                  ("P04", 71.1, (0.62, 0.88, 0.74), (0.10, 0.48, 0.30))]

    # First draw the lower (exploded) 3D LED Clip + Strip at y = 18 mm, z_offset = -22 mm (before snapping up)
    y_exp = 16.0
    z_exp = 4.0
    # 3D clip carrier bar
    clip_face_front = [iso_detail(-4, y_exp - 3, z_exp), iso_detail(82, y_exp - 3, z_exp),
                       iso_detail(82, y_exp - 3, z_exp + 5), iso_detail(-4, y_exp - 3, z_exp + 5)]
    clip_face_top = [iso_detail(-4, y_exp - 3, z_exp + 5), iso_detail(82, y_exp - 3, z_exp + 5),
                     iso_detail(82, y_exp + 3, z_exp + 5), iso_detail(-4, y_exp + 3, z_exp + 5)]
    c.fill_rgb(0.22, 0.62, 0.88)
    c.stroke_rgb(0.08, 0.35, 0.58)
    c.line_width(0.9)
    c.poly(clip_face_front, close=True, fill=True, stroke=True)
    c.fill_rgb(0.35, 0.72, 0.95)
    c.poly(clip_face_top, close=True, fill=True, stroke=True)

    # Black WS2812B LED strip lying inside the 3D clip bar
    strip_top = [iso_detail(-8, y_exp - 2, z_exp + 5.2), iso_detail(84, y_exp - 2, z_exp + 5.2),
                 iso_detail(84, y_exp + 2, z_exp + 5.2), iso_detail(-8, y_exp + 2, z_exp + 5.2)]
    c.fill_rgb(0.15, 0.16, 0.18)
    c.stroke_rgb(0.05, 0.05, 0.05)
    c.poly(strip_top, close=True, fill=True, stroke=True)

    # 3-wire cable coming out on the left (x < -8)
    w_cols = [((0.90, 0.15, 0.15), "5V (Rot)"), ((0.95, 0.95, 0.95), "Din (Weiss -> Pin 2..9)"), ((0.15, 0.15, 0.18), "GND (Schwarz)")]
    for w_idx, (wcol, _) in enumerate(w_cols):
        wy = y_exp - 1.5 + w_idx * 1.5
        p1 = iso_detail(-8, wy, z_exp + 5.2)
        p2 = iso_detail(-20, wy - 2, z_exp + 2.0)
        c.stroke_rgb(*wcol)
        c.line_width(1.8 if w_idx != 1 else 2.2)
        c.line(p1[0], p1[1], p2[0], p2[1])
    lbl_cab = iso_detail(-18, y_exp, z_exp - 2)
    c.text(lbl_cab[0] - 2, lbl_cab[1] - 8, "Kabel LINKS", size=7.2, bold=True, rgb=(0.78, 0.18, 0.05), align="center")
    c.text(lbl_cab[0] - 2, lbl_cab[1] - 16, "(an Pin 2..9)", size=6.5, bold=True, rgb=(0.15, 0.20, 0.30), align="center")

    # Draw clip jaws & LEDs on the exploded strip
    for g_idx, (gx_c, col_n, led_lbl) in enumerate([(9.2, "rot", "LED 1"), (27.3, "orange", "LED 2"), (44.8, "blau", "LED 3"), (62.4, "gelb", "LED 4")]):
        lp = iso_detail(gx_c, y_exp, z_exp + 5.6)
        cr, cg, cb = COLOR_MAP[col_n]
        c.fill_rgb(cr, cg, cb)
        c.stroke_rgb(1, 1, 1)
        c.line_width(0.6)
        c.circle(lp[0], lp[1], 3.8, fill=True, stroke=True)
        c.text(lp[0], lp[1] - 11, led_lbl, size=6.2, bold=True, rgb=(0.11, 0.18, 0.30), align="center")

    # Upward assembly arrows from the exploded clip to the bottom of the rails
    for _, rx, _, _ in rail_infos[1:]:
        a_bot = iso_detail(rx, y_exp, z_exp + 7.0)
        a_top = iso_detail(rx, y_exp, 25.0)
        c.arrow(a_bot[0], a_bot[1], a_top[0], a_top[1], head=5.0, color=(0.85, 0.15, 0.10), lw=1.5)

    # Now draw the 5 vertical 20mm wave rails (S-L, P01..P04) at z = 26..56 mm
    for rname, rx, fc, sc_col in rail_infos:
        # Rail goes from y = 5 to y = 58, with slope z_top(y) = 46 + 0.25*y and z_bot(y) = z_top(y) - 20
        r_pts = [
            iso_detail(rx, 6.0, 26.0),
            iso_detail(rx, 58.0, 40.0),
            iso_detail(rx, 58.0, 60.0),
            iso_detail(rx, 6.0, 46.0),
        ]
        c.fill_rgb(*fc)
        c.stroke_rgb(*sc_col)
        c.line_width(1.0)
        c.poly(r_pts, close=True, fill=True, stroke=True)
        top_lbl = iso_detail(rx, 54.0, 62.0)
        c.text(top_lbl[0], top_lbl[1], rname, size=7.2, bold=True, rgb=sc_col, align="center")

    # Draw a SECOND already-mounted LED strip at y = 42 mm snapped onto the bottom edge of the rails!
    y_mnt = 42.0
    z_mnt_bot = 26.0 + (y_mnt - 6.0) * (14.0 / 52.0)  # exact bottom edge of the 20mm rail at y=42
    mnt_front = [iso_detail(-4, y_mnt - 2.5, z_mnt_bot - 2.5), iso_detail(82, y_mnt - 2.5, z_mnt_bot - 2.5),
                 iso_detail(82, y_mnt - 2.5, z_mnt_bot + 1.5), iso_detail(-4, y_mnt - 2.5, z_mnt_bot + 1.5)]
    c.fill_rgb(0.18, 0.20, 0.24)
    c.stroke_rgb(0.95, 0.55, 0.10)
    c.line_width(1.0)
    c.poly(mnt_front, close=True, fill=True, stroke=True)
    for gx_c, col_n in [(9.2, "orange"), (27.3, "rot"), (44.8, "gelb"), (62.4, "blau")]:
        lp = iso_detail(gx_c, y_mnt, z_mnt_bot + 2.0)
        cr, cg, cb = COLOR_MAP[col_n]
        c.fill_rgb(cr, cg, cb)
        c.stroke_rgb(1, 1, 1)
        c.line_width(0.5)
        c.circle(lp[0], lp[1], 3.4, fill=True, stroke=True)

    lbl_mnt_target = iso_detail(27.3, y_mnt, z_mnt_bot + 3.0)
    c.fill_rgb(1.0, 0.96, 0.90)
    c.stroke_rgb(0.85, 0.35, 0.08)
    c.line_width(0.8)
    c.rect(512.0, 474.0, 298.0, 16.0, fill=True, stroke=True)
    c.text(661.0, 479.0, "Oben im Bild: Fertig von unten auf P01..P16 geklipste LED-Reihe (20 mm unter Papier)", size=6.5, bold=True, rgb=(0.75, 0.20, 0.05), align="center")
    c.arrow(661.0, 474.0, lbl_mnt_target[0], lbl_mnt_target[1] + 5.0, head=4.5, color=(0.85, 0.25, 0.08), lw=1.1)

    # Bottom right: 3 clear visual step boxes explaining the 3D attachment
    box_y = 28.0
    box_h = 212.0
    c.fill_rgb(0.95, 0.97, 1.0)
    c.stroke_rgb(0.22, 0.50, 0.80)
    c.line_width(1.0)
    c.rect(508, box_y, 306, box_h, fill=True, stroke=True)

    c.text(518, box_y + box_h - 16, "So bindet ihr die 8 Reihen (S1..S8) im 3D-Modell an:", size=8.8, bold=True, rgb=(0.08, 0.22, 0.45))

    vsteps = [
        ("1", "Von UNTEN an die 16 Schienen P01..P16 stecken",
         "Die 16 Schienen P01..P16 sind überall genau 20 mm hoch.",
         "Steckt jede LED-Reihe S1..S8 von UNTEN an die Unterkante der",
         "Schienen (sodass oben die Papierschicht glatt aufliegen kann)."),
        ("2", "Kabel-Anfang LINKS bei S-L & LED 9 in der Mitte",
         "Das 3-polige Kabel (5V/Din/GND) liegt immer LINKS bei S-L.",
         "Drückt LED Nr. 9 zuerst mittig zwischen P08 und P09 (Lücke 9)",
         "ein: Dann sitzen LED 1..17 automatisch in Lücke 1..17!"),
        ("3", "Abstände ab Querband Q5, Q4 und Q2 einhalten",
         "Oberes Feld vor Q5: S1 (17mm), S2 (34mm), S3 (51mm),",
         "S4 (68mm), S5 (86mm), S6 (104mm vor Q5).",
         "Mittleres Feld: S7 (21mm vor Q4). Unteres Feld: S8 (13mm vor Q2)."),
    ]
    sy = box_y + box_h - 36
    for badge_n, st_title, l1, l2, l3 in vsteps:
        c.step_badge(524, sy - 6, badge_n, bg=(0.12, 0.38, 0.72), r=8.5)
        c.text(537, sy, st_title, size=7.8, bold=True, rgb=(0.11, 0.18, 0.30))
        c.text(537, sy - 11, l1, size=6.9, rgb=(0.20, 0.22, 0.26))
        c.text(537, sy - 20, l2, size=6.9, rgb=(0.20, 0.22, 0.26))
        c.text(537, sy - 29, l3, size=6.9, bold=True, rgb=(0.15, 0.32, 0.55))
        sy -= 61


def draw_page1(c, lr, top_curves):
    c.fill_rgb(0.98, 0.98, 0.99)
    c.rect(0, 0, W_PT, H_PT, fill=True, stroke=False)

    # Header bar
    c.fill_rgb(0.11, 0.18, 0.30)
    c.rect(0, H_PT - 48, W_PT, 48, fill=True, stroke=False)
    c.text(24, H_PT - 26, "SEITE 2/4: BELEGUNGSPLAN & MASS-TABELLE DER 8 LED-REIHEN (S1..S8 AN PIN 2..9)", size=13.5, bold=True, rgb=(1, 1, 1))
    c.text(24, H_PT - 41, "Alle 109 Hai-Signale verteilt auf 8 WS2812B-Streifen | Je Strang 10 bis max. 16 aktive LEDs in den 17 Schienen-Luecken", size=9.2, rgb=(0.82, 0.90, 1.0))

    # Left card: Matrix of 8 LED strips x 20 LEDs (1..17 inside model gaps, 18..20 overhang)
    c.fill_rgb(1, 1, 1)
    c.stroke_rgb(0.80, 0.84, 0.88)
    c.line_width(1.0)
    c.rect(18, 20, 444, 515, fill=True, stroke=True)

    c.text(28, 516, "1. Raster-Plan (Vorderansicht): Welche LED (1..17) leuchtet in welcher Schienen-Luecke?", size=10.0, bold=True, rgb=(0.11, 0.18, 0.30))
    c.text(28, 502, "Kabel-Einspeisung (5V/Din/GND) links bei S-L (Luecke 1 = LED 1). LED 9 liegt exakt in der Modellmitte (Luecke 9, x=150 mm).", size=7.6, rgb=(0.3, 0.33, 0.38))

    gx0 = 76.0
    gw = 18.2
    gy_top = 460.0
    row_h = 46.5

    c.text(25, gy_top + 16, "LED/Luecke:", size=7.2, bold=True, rgb=(0.2, 0.25, 0.3))
    c.text(25, gy_top + 4, "Schiene:", size=6.8, rgb=(0.45, 0.48, 0.52))
    for g in range(1, 21):
        cx = gx0 + (g - 0.5) * gw
        col_rgb = (0.1, 0.15, 0.25) if g <= 17 else (0.55, 0.55, 0.58)
        c.text(cx, gy_top + 16, f"{g}", size=7.5, bold=(g <= 17), rgb=col_rgb, align="center")
        if g <= 16:
            rx = gx0 + g * gw
            c.stroke_rgb(0.75, 0.55, 0.30)
            c.line_width(1.2)
            c.line(rx, gy_top - 8 * row_h - 4, rx, gy_top + 12)
            c.text(rx, gy_top + 4, f"P{g:02d}", size=5.6, bold=True, rgb=(0.55, 0.38, 0.15), align="center")

    ox = gx0 + 17 * gw
    c.stroke_rgb(0.85, 0.2, 0.2)
    c.dash((3, 2), 0)
    c.line(ox, gy_top - 8 * row_h - 4, ox, gy_top + 24)
    c.dash((), 0)
    c.text(ox + 1.5 * gw, gy_top + 25, "Rechts ausserhalb S-R", size=6.2, bold=True, rgb=(0.75, 0.2, 0.2), align="center")

    active_map = {(s["strang"], s["luecke"]): s for s in lr["sharks"]}

    for idx, r in enumerate(lr["rows"]):
        sid = r["strang"]
        ry = gy_top - (idx + 1) * row_h + 10

        if sid in ("S7", "S8"):
            q_name = "Querband Q4 (y = 145,8 mm)" if sid == "S7" else "Querbaender Q3 (y = 95,2 mm) & Q2 (y = 54,9 mm)"
            qy = ry + row_h - 8.0
            c.stroke_rgb(0.20, 0.55, 0.35)
            c.line_width(1.3)
            c.dash((4, 2), 0)
            c.line(25, qy, gx0 + 17 * gw, qy)
            c.dash((), 0)
            c.fill_rgb(0.90, 0.97, 0.92)
            c.rect(gx0 + 3.5 * gw, qy - 5.0, 10 * gw, 10, fill=True, stroke=False)
            c.text(gx0 + 8.5 * gw, qy - 2.5, q_name, size=6.4, bold=True, rgb=(0.12, 0.45, 0.25), align="center")

        c.text(25, ry + 14, f"{sid} (Pin {r['arduino_pin']})", size=8.3, bold=True, rgb=(0.11, 0.18, 0.30))
        c.text(25, ry + 3, f"y={r['y_mm']:.0f} | z={r['z_oberflaeche_mittel_mm']:.0f}mm", size=6.4, rgb=(0.35, 0.38, 0.42))

        c.fill_rgb(0.16, 0.17, 0.20)
        c.rect(gx0, ry + 2, 20 * gw, 20, fill=True, stroke=False)

        for g in range(1, 21):
            cx = gx0 + (g - 0.5) * gw
            shark = active_map.get((sid, g)) if g <= 17 else None
            if shark:
                cr, cg, cb = COLOR_MAP[shark["farbe"]]
                c.fill_rgb(cr, cg, cb)
                c.stroke_rgb(1, 1, 1)
                c.line_width(0.8)
                c.rect(cx - 6.0, ry + 5.8, 12.0, 12.4, fill=True, stroke=True)
                txt_rgb = (0.1, 0.1, 0.1) if shark["farbe"] in ("gelb", "orange") else (1, 1, 1)
                c.text(cx, ry + 9.8, f"{shark['led_id']}", size=6.0, bold=True, rgb=txt_rgb, align="center")
            else:
                c.fill_rgb(0.30, 0.32, 0.35)
                c.stroke_rgb(0.45, 0.47, 0.50)
                c.line_width(0.4)
                c.rect(cx - 3.8, ry + 8.0, 7.6, 8.0, fill=True, stroke=True)

    ly = 30
    c.text(28, ly + 22, "Farbcode (IUCN Rote Liste) & Zahl im Kasten = Hai-ID (led_id 1..109):", size=7.8, bold=True, rgb=(0.15, 0.18, 0.22))
    legend_items = [
        ("rot", "Rot = CR (vom Aussterben bedr.)", 118),
        ("orange", "Orange = EN (stark gefaehrdet)", 108),
        ("gelb", "Gelb = VU (gefaehrdet)", 88),
        ("blau", "Blau = LC/NT/DD (nicht gef.)", 100),
    ]
    lx = 28
    for key, label, step_w in legend_items:
        cr, cg, cb = COLOR_MAP[key]
        c.fill_rgb(cr, cg, cb)
        c.rect(lx, ly + 4, 9.0, 9.0, fill=True, stroke=False)
        c.text(lx + 11, ly + 6, label, size=6.6, rgb=(0.2, 0.22, 0.25))
        lx += step_w

    # Right card: Exact Ruler Measurement Table for S1..S8
    c.fill_rgb(1, 1, 1)
    c.stroke_rgb(0.80, 0.84, 0.88)
    c.line_width(1.0)
    c.rect(470, 20, 354, 515, fill=True, stroke=True)

    c.fill_rgb(0.92, 0.96, 1.0)
    c.stroke_rgb(0.20, 0.48, 0.80)
    c.rect(480, 446, 334, 78, fill=True, stroke=True)
    c.text(488, 511, "Kurz-Zusammenfassung zum direkten Anbinden:", size=9.8, bold=True, rgb=(0.08, 0.22, 0.45))
    c.text(488, 496, "- 8 LED-Streifen (S1..S8) -> direkt an Arduino Digital-Pin 2 bis Pin 9.", size=7.8, bold=True, rgb=(0.12, 0.16, 0.22))
    c.text(488, 483, "- Kabel-Anfang (Din) immer LINKS bei Seitenwand S-L (LED 1 = Luecke 1).", size=7.8, bold=True, rgb=(0.12, 0.16, 0.22))
    c.text(488, 470, "- LED 1 bis LED 17 sitzen in Luecke 1 bis 17; LED 18+ haengen rechts raus.", size=7.8, bold=True, rgb=(0.12, 0.16, 0.22))
    c.text(488, 456, "- Unten in der Tabelle stehen die exakten Lineal-Masse zum Anzeichnen!", size=7.8, bold=True, rgb=(0.08, 0.45, 0.22))

    c.text(480, 428, "2. Lineal-Masstabelle fuer alle 8 Reihen (Position y, Abstand Q & Hoehe z)", size=9.6, bold=True, rgb=(0.11, 0.18, 0.30))

    ty = 408
    c.fill_rgb(0.16, 0.24, 0.36)
    c.rect(480, ty, 334, 18, fill=True, stroke=False)
    c.text(484, ty + 5, "Reihe/Pin", size=7.2, bold=True, rgb=(1, 1, 1))
    c.text(528, ty + 5, "LEDs", size=7.2, bold=True, rgb=(1, 1, 1))
    c.text(556, ty + 5, "Tiefe (m)", size=7.2, bold=True, rgb=(1, 1, 1))
    c.text(606, ty + 5, "y (v. vorn)", size=7.2, bold=True, rgb=(1, 1, 1))
    c.text(654, ty + 5, "Abstand ab Q", size=7.2, bold=True, rgb=(1, 1, 1))
    c.text(726, ty + 5, "z Papier (L/M/R)", size=7.2, bold=True, rgb=(1, 1, 1))

    for idx, r in enumerate(lr["rows"]):
        sid = r["strang"]
        yc = r["y_mm"]
        z_l = interp_curve(top_curves["P01"], yc)
        z_m = interp_curve(top_curves["P08"], yc)
        z_r = interp_curve(top_curves["P16"], yc)

        ry = ty - (idx + 1) * 30
        bg = (0.95, 0.97, 0.99) if idx % 2 == 0 else (1.0, 1.0, 1.0)
        if r["anzahl_aktive_leds"] >= 16:
            bg = (1.0, 0.95, 0.86)
        c.fill_rgb(*bg)
        c.stroke_rgb(0.86, 0.88, 0.91)
        c.line_width(0.5)
        c.rect(480, ry, 334, 30, fill=True, stroke=True)

        c.text(484, ry + 16, f"{sid}", size=8.5, bold=True, rgb=(0.11, 0.18, 0.30))
        c.text(484, ry + 5, f"Pin {r['arduino_pin']}", size=6.8, bold=True, rgb=(0.75, 0.20, 0.05))
        c.text(540, ry + 11, f"{r['anzahl_aktive_leds']}/17", size=8.0, bold=True, rgb=(0.15, 0.18, 0.22), align="center")
        c.text(556, ry + 11, f"{r['tiefe_min_m']:.0f}-{r['tiefe_max_m']:.0f}m", size=7.2, rgb=(0.2, 0.22, 0.25))
        c.text(606, ry + 16, f"y={yc:.0f} mm", size=7.6, bold=True, rgb=(0.11, 0.18, 0.30))
        c.text(606, ry + 5, f"v. Q5: {264.8 - yc:.0f}mm", size=6.2, rgb=(0.4, 0.42, 0.45))
        c.text(654, ry + 11, r["bezug_querband"], size=6.8, bold=True, rgb=(0.12, 0.42, 0.22))
        c.text(726, ry + 16, f"Ø z = {r['z_oberflaeche_mittel_mm']:.0f} mm", size=7.6, bold=True, rgb=(0.08, 0.25, 0.50))
        c.text(726, ry + 5, f"{z_l:.0f} / {z_m:.0f} / {z_r:.0f} mm", size=6.3, rgb=(0.35, 0.38, 0.42))

    # Practical marking guide at bottom right
    c.fill_rgb(0.96, 0.97, 0.98)
    c.stroke_rgb(0.75, 0.78, 0.82)
    c.rect(480, 28, 334, 130, fill=True, stroke=True)
    c.text(488, 144, "So zeichnet ihr die 8 Positionen in 60 Sekunden mit dem Lineal an:", size=8.5, bold=True, rgb=(0.11, 0.18, 0.30))
    c.text(488, 129, "1. Messt oben ab Querband Q5 (y = 264,8 mm) nach vorne Richtung Tiefsee:", size=7.4, rgb=(0.2, 0.22, 0.25))
    c.text(488, 118, "   - S1 bei 17 mm vor Q5  |  S2 bei 34 mm vor Q5  |  S3 bei 51 mm vor Q5", size=7.4, bold=True, rgb=(0.11, 0.18, 0.30))
    c.text(488, 107, "   - S4 bei 68 mm vor Q5  |  S5 bei 86 mm vor Q5  |  S6 bei 104 mm vor Q5 (15 mm hinter Q4)", size=7.4, bold=True, rgb=(0.11, 0.18, 0.30))
    c.text(488, 93, "2. Messt ab Querband Q4 (y = 145,8 mm) nach vorne Richtung Tiefsee:", size=7.4, rgb=(0.2, 0.22, 0.25))
    c.text(488, 82, "   - S7 bei 21 mm vor Q4 (y = 125 mm, mittig im Feld zwischen Q3 und Q4)", size=7.4, bold=True, rgb=(0.11, 0.18, 0.30))
    c.text(488, 68, "3. Messt ab Querband Q2 (y = 54,9 mm) nach vorne Richtung Tiefsee:", size=7.4, rgb=(0.2, 0.22, 0.25))
    c.text(488, 57, "   - S8 bei 13 mm vor Q2 (y = 42 mm, im Feld zwischen Q1 und Q2)", size=7.4, bold=True, rgb=(0.11, 0.18, 0.30))
    c.text(488, 39, "Hinweis: Die Clip-Unterkante an den Schienen P01..P16 liegt immer genau 20 mm unter z Papier!", size=7.2, bold=True, rgb=(0.75, 0.20, 0.05))


def draw_page2(c, lr, top_curves):
    c.fill_rgb(0.98, 0.98, 0.99)
    c.rect(0, 0, W_PT, H_PT, fill=True, stroke=False)

    c.fill_rgb(0.11, 0.18, 0.30)
    c.rect(0, H_PT - 48, W_PT, 48, fill=True, stroke=False)
    c.text(24, H_PT - 26, "SEITE 3/4: SEITENSCHNITT, 3D-CLIP-MONTAGE & ARDUINO-VERKABELUNG (PIN 2..9)", size=13.5, bold=True, rgb=(1, 1, 1))
    c.text(24, H_PT - 41, "8x 3D-Clip von unten auf P01..P16 stecken | Streifen einschieben | 8 Datenleitungen an Pin 2..9 + gemeinsame 5V/GND", size=9.2, rgb=(0.82, 0.90, 1.0))

    c.fill_rgb(1, 1, 1)
    c.stroke_rgb(0.80, 0.84, 0.88)
    c.line_width(1.0)
    c.rect(20, 20, 415, 515, fill=True, stroke=True)

    c.text(32, 516, "3. Seitenansicht (Schnitt entlang Schiene P08): Position der 8 Straenge S1..S8", size=10.0, bold=True, rgb=(0.11, 0.18, 0.30))
    c.text(32, 502, "Alle 8 LED-Clip-Bruecken sitzen kollisionsfrei an der Unterkante der 20 mm Schienen P01..P16.", size=8.0, rgb=(0.3, 0.33, 0.38))

    sx = 345.0 / 285.0
    sz = 345.0 / 285.0
    ox, oz = 55.0, 75.0

    def to_side(y, z):
        return ox + y * sx, oz + z * sz

    for z_mm in range(0, 275, 50):
        _, py = to_side(0, z_mm)
        c.stroke_rgb(0.90, 0.92, 0.94)
        c.line_width(0.5)
        c.line(ox, py, ox + 281 * sx, py)
        c.text(ox - 4, py - 2.5, f"{z_mm}mm", size=6.5, rgb=(0.45, 0.48, 0.52), align="right")

    p_fl0 = to_side(0, -2)
    p_fl1 = to_side(281, 0)
    c.fill_rgb(0.76, 0.62, 0.44)
    c.stroke_rgb(0.45, 0.32, 0.18)
    c.line_width(0.8)
    c.rect(p_fl0[0], p_fl0[1], p_fl1[0] - p_fl0[0], 3.0, fill=True, stroke=True)
    c.text(ox + 140 * sx, oz - 14, "Bodenplatte B (y = 0 .. 280,6 mm)", size=7.5, bold=True, rgb=(0.45, 0.32, 0.18), align="center")

    p08_top = top_curves["P08"]
    top_poly = [to_side(u, z) for u, z in p08_top[::4]]
    bot_poly = [to_side(u, max(0.0, z - 20.0)) for u, z in reversed(p08_top[::4])]
    c.fill_rgb(0.90, 0.78, 0.58)
    c.stroke_rgb(0.55, 0.40, 0.20)
    c.line_width(1.0)
    c.poly(top_poly + bot_poly, close=True, fill=True, stroke=True)

    paper_pts = [to_side(u, z + 2.2) for u, z in p08_top[::4]]
    c.stroke_rgb(0.15, 0.45, 0.85)
    c.line_width(2.0)
    c.dash((5, 2), 0)
    c.poly(paper_pts, close=False, fill=False, stroke=True)
    c.dash((), 0)
    c.text(ox + 115 * sx, oz + 235 * sz, "Papierschicht vorne auf P01..P16", size=8.0, bold=True, rgb=(0.12, 0.40, 0.80))

    q_ys = [("Q1", 21.9), ("Q2", 54.9), ("Q3", 95.2), ("Q4", 145.8), ("Q5", 264.8)]
    for qid, qy in q_ys:
        qz = interp_curve(p08_top, qy)
        px, py_top = to_side(qy, qz)
        _, py_bot = to_side(qy, max(0.0, qz - 20.0))
        c.fill_rgb(0.20, 0.65, 0.35)
        c.stroke_rgb(0.10, 0.40, 0.20)
        c.line_width(0.8)
        c.rect(px - 2.0, py_bot, 4.0, py_top - py_bot, fill=True, stroke=True)
        c.text(px, py_top + 6, qid, size=7.2, bold=True, rgb=(0.10, 0.45, 0.20), align="center")

    for r in lr["rows"]:
        sid = r["strang"]
        ry_mm = r["y_mm"]
        rz = interp_curve(p08_top, ry_mm)
        px, py_top = to_side(ry_mm, rz)
        _, py_bot = to_side(ry_mm, max(0.0, rz - 20.0))

        c.fill_rgb(0.95, 0.35, 0.10)
        c.stroke_rgb(0.65, 0.15, 0.0)
        c.line_width(0.7)
        c.rect(px - 5.5, py_bot - 4.5, 11.0, 8.5, fill=True, stroke=True)

        c.stroke_rgb(0.95, 0.55, 0.05)
        c.line_width(1.4)
        c.line(px, py_bot + 4.0, px, py_top + 1.0)

        c.text(px, py_bot - 13, sid, size=7.0, bold=True, rgb=(0.75, 0.20, 0.05), align="center")
        c.text(px, py_bot - 21, f"Pin {r['arduino_pin']}", size=5.8, rgb=(0.2, 0.25, 0.35), align="center")
        c.text(px, py_bot - 28, f"y={ry_mm:.0f}", size=5.5, rgb=(0.4, 0.4, 0.45), align="center")

    c.text(ox + 150 * sx, oz + 55 * sz, "Freier Raum unter den 20 mm Schienen", size=9.0, bold=True, rgb=(0.35, 0.40, 0.48), align="center")
    c.text(ox + 150 * sx, oz + 42 * sz, "(hier werden die 8 LED-Clip-Leisten S1..S8 von unten aufgesteckt)", size=7.8, rgb=(0.35, 0.40, 0.48), align="center")

    # Right panel: Detail cross-section
    c.fill_rgb(1, 1, 1)
    c.stroke_rgb(0.80, 0.84, 0.88)
    c.line_width(1.0)
    c.rect(445, 20, 377, 515, fill=True, stroke=True)

    c.text(457, 516, "4. Detail-Querschnitt: 3D-Clip-Traeger & Elektrischer Anschluss", size=10.0, bold=True, rgb=(0.11, 0.18, 0.30))
    c.text(457, 502, "Von unten auf P01..P16 geklipst: Papier bleibt glatt, jede Luecke hat ihren eigenen Lichtkamin!", size=8.0, rgb=(0.3, 0.33, 0.38))

    dx0 = 475.0
    dy0 = 265.0
    scale_d = 4.6

    paper_y = dy0 + 20.5 * scale_d
    c.fill_rgb(0.95, 0.96, 0.98)
    c.stroke_rgb(0.15, 0.45, 0.85)
    c.line_width(2.0)
    c.rect(dx0 - 10, paper_y, 335, 6, fill=True, stroke=True)
    c.text(dx0 + 155, paper_y + 11, "Vordere Papierschicht (liegt glatt auf den Oberkanten von P01..P16 auf)", size=8.0, bold=True, rgb=(0.12, 0.40, 0.80), align="center")

    c.fill_rgb(0.22, 0.62, 0.88)
    c.stroke_rgb(0.10, 0.38, 0.60)
    c.line_width(1.2)
    c.rect(dx0 - 5, dy0 - 4.5 * scale_d, 325, 2.3 * scale_d, fill=True, stroke=True)

    c.fill_rgb(0.15, 0.16, 0.18)
    c.stroke_rgb(0.05, 0.05, 0.05)
    c.rect(dx0 - 12, dy0 - 2.2 * scale_d, 340, 1.7 * scale_d, fill=True, stroke=True)
    c.text(dx0 + 155, dy0 - 3.8 * scale_d, "WS2812B LED-Streifen (10 mm breit, Raster 16,67 mm) in 10,4 mm Einschub-Rinne", size=6.6, bold=True, rgb=(1, 1, 1), align="center")

    for k in range(4):
        rx_center = dx0 + 35.0 + k * 17.53 * scale_d
        rw = 2.0 * scale_d
        rh = 20.0 * scale_d

        jw = 1.8 * scale_d
        jh = 10.5 * scale_d
        c.fill_rgb(0.22, 0.62, 0.88)
        c.stroke_rgb(0.10, 0.38, 0.60)
        c.rect(rx_center - rw / 2 - jw, dy0, jw, jh, fill=True, stroke=True)
        c.rect(rx_center + rw / 2, dy0, jw, jh, fill=True, stroke=True)

        c.fill_rgb(0.86, 0.72, 0.50)
        c.stroke_rgb(0.48, 0.34, 0.16)
        c.line_width(1.2)
        c.rect(rx_center - rw / 2, dy0, rw, rh, fill=True, stroke=True)
        c.text(rx_center, dy0 + rh - 14, f"P{k+7:02d}", size=7.5, bold=True, rgb=(0.38, 0.24, 0.08), align="center")
        c.text(rx_center, dy0 + rh - 24, "2mm", size=6.2, rgb=(0.45, 0.30, 0.12), align="center")

    gap_demos = [
        (0, "Luecke 8 (17,53 mm)", "orange", "Hai-LED aktiv (EN)", True),
        (1, "Luecke 9 (Mitte)", "rot", "Hai-LED aktiv (CR)", True),
        (2, "Luecke 10", None, "LED dunkel (0,0,0)", False),
    ]
    for k, g_title, col_name, status_txt, is_on in gap_demos:
        gx_center = dx0 + 35.0 + (k + 0.5) * 17.53 * scale_d
        led_x = gx_center + (k - 1) * (16.67 - 17.53) * scale_d

        if is_on:
            cr, cg, cb = COLOR_MAP[col_name]
            cone = [
                (led_x - 3.0 * scale_d, dy0 + 1.2 * scale_d),
                (led_x + 3.0 * scale_d, dy0 + 1.2 * scale_d),
                (gx_center + 5.8 * scale_d, paper_y),
                (gx_center - 5.8 * scale_d, paper_y),
            ]
            c.fill_rgb(min(1.0, cr * 0.35 + 0.65), min(1.0, cg * 0.35 + 0.65), min(1.0, cb * 0.35 + 0.65))
            c.stroke_rgb(cr, cg, cb)
            c.line_width(0.8)
            c.poly(cone, close=True, fill=True, stroke=True)

            c.fill_rgb(cr, cg, cb)
            c.rect(gx_center - 5.5 * scale_d, paper_y + 0.5, 11.0 * scale_d, 5.0, fill=True, stroke=False)
        else:
            c.fill_rgb(0.40, 0.42, 0.45)

        c.stroke_rgb(0.2, 0.2, 0.2)
        c.line_width(0.8)
        c.rect(led_x - 2.5 * scale_d, dy0 - 0.5 * scale_d, 5.0 * scale_d, 1.7 * scale_d, fill=True, stroke=True)
        c.text(gx_center, dy0 + 14.5 * scale_d, g_title, size=7.2, bold=True, rgb=(0.15, 0.20, 0.28), align="center")
        c.text(gx_center, dy0 + 12.2 * scale_d, status_txt, size=6.8, bold=is_on,
               rgb=(0.75, 0.15, 0.05) if is_on else (0.45, 0.48, 0.52), align="center")

    c.fill_rgb(0.95, 0.97, 1.0)
    c.stroke_rgb(0.22, 0.50, 0.80)
    c.line_width(1.0)
    c.rect(457, 28, 353, 197, fill=True, stroke=True)

    c.text(468, 210, "Montage & Verkabelung der 8 Reihen (S1..S8) Schritt fuer Schritt:", size=9.2, bold=True, rgb=(0.08, 0.22, 0.45))

    steps = [
        ("SCHRITT 1: Ausrichtung der 8 LED-Streifen (Kabel immer LINKS bei S-L)",
         "Legt das Modell so vor euch, dass S-L links (x = 0 mm) und S-R rechts (x = 300 mm) ist.",
         "Das 3-polige Anschlusskabel (Rot=5V, Weiss=Din, Schwarz=GND) zeigt bei allen 8 Streifen nach LINKS."),
        ("SCHRITT 2: Aufstecken bei den 8 Lineal-Positionen (S1..S8)",
         "Steckt S1..S6 im oberen Feld (17, 34, 51, 68, 86, 104 mm vor Q5), S7 (21 mm vor Q4) und",
         "S8 (13 mm vor Q2) von unten auf die 16 Schienen P01..P16. Richtet LED Nr. 9 auf Luecke 9 (Mitte) aus."),
        ("SCHRITT 3: 8 Datenkabel an Arduino Pin 2..9 & gemeinsame Stromversorgung",
         "Rot (+5V) und Schwarz (GND) aller 8 Streifen auf die gemeinsame 5V/GND-Schiene am Breadboard.",
         "Datenleitung (Din): S1->Pin2, S2->Pin3, S3->Pin4, S4->Pin5, S5->Pin6, S6->Pin7, S7->Pin8, S8->Pin9."),
    ]
    sy = 190
    for title, l1, l2 in steps:
        c.text(468, sy, title, size=8.0, bold=True, rgb=(0.11, 0.18, 0.30))
        c.text(474, sy - 12, l1, size=7.2, rgb=(0.2, 0.22, 0.26))
        c.text(474, sy - 22, l2, size=7.2, rgb=(0.2, 0.22, 0.26))
        sy -= 54


def draw_page3(c, lr):
    """Page 4: Detailed per-strip reference cards (S1..S8) listing every active LED (1..17), gap, color, depth, and species."""
    c.fill_rgb(0.98, 0.98, 0.99)
    c.rect(0, 0, W_PT, H_PT, fill=True, stroke=False)

    c.fill_rgb(0.11, 0.18, 0.30)
    c.rect(0, H_PT - 48, W_PT, 48, fill=True, stroke=False)
    c.text(24, H_PT - 26, "SEITE 4/4: KOMPLETTE CHECKLISTE ALLER 8 REIHEN (S1..S8) & ALLER 109 HAI-SIGNALE", size=13.5, bold=True, rgb=(1, 1, 1))
    c.text(24, H_PT - 41, "Jede Karte zeigt fuer einen Strang (S1..S8): Arduino-Pin, Einbau-Ort (y, z) und welche LED-Nummern (1..17) in welcher Farbe leuchten", size=9.2, rgb=(0.82, 0.90, 1.0))

    sharks_by_row = {r["strang"]: [] for r in lr["rows"]}
    for s in lr["sharks"]:
        sharks_by_row[s["strang"]].append(s)

    # 4 columns x 2 rows of cards (8 cards total for S1..S8)
    card_w = 196.0
    card_h = 252.0
    margin_x = 18.0
    gap_x = 8.0
    row_y = [282.0, 20.0]

    for idx, r in enumerate(lr["rows"]):
        col = idx % 4
        row = idx // 4
        cx = margin_x + col * (card_w + gap_x)
        cy = row_y[row]
        sid = r["strang"]

        c.fill_rgb(1, 1, 1)
        c.stroke_rgb(0.76, 0.80, 0.86)
        c.line_width(0.9)
        c.rect(cx, cy, card_w, card_h, fill=True, stroke=True)

        # Card header
        c.fill_rgb(0.15, 0.24, 0.38)
        c.rect(cx, cy + card_h - 34, card_w, 34, fill=True, stroke=False)
        c.text(cx + 7, cy + card_h - 14, f"{sid} (Arduino Pin {r['arduino_pin']}) - {r['anzahl_aktive_leds']} LEDs",
               size=8.8, bold=True, rgb=(1, 1, 1))
        c.text(cx + 7, cy + card_h - 25, f"y={r['y_mm']:.0f}mm ({r['bezug_querband']}) | z={r['z_oberflaeche_mittel_mm']:.0f}mm",
               size=6.6, rgb=(0.82, 0.90, 1.0))
        c.text(cx + 7, cy + card_h - 33, f"Tiefe: {r['tiefe_min_m']:.0f}-{r['tiefe_max_m']:.0f} m | Frei: " +
               ",".join(str(g) for g in range(1, 18) if g not in {s["luecke"] for s in sharks_by_row[sid]}),
               size=5.8, rgb=(0.95, 0.88, 0.65))

        # Column headers inside card
        hy = cy + card_h - 44
        c.fill_rgb(0.92, 0.94, 0.97)
        c.rect(cx + 2, hy, card_w - 4, 10, fill=True, stroke=False)
        c.text(cx + 6, hy + 2.5, "LED#", size=6.0, bold=True, rgb=(0.2, 0.22, 0.28))
        c.text(cx + 28, hy + 2.5, "Schienen", size=6.0, bold=True, rgb=(0.2, 0.22, 0.28))
        c.text(cx + 64, hy + 2.5, "Farbe", size=6.0, bold=True, rgb=(0.2, 0.22, 0.28))
        c.text(cx + 88, hy + 2.5, "Tiefe", size=6.0, bold=True, rgb=(0.2, 0.22, 0.28))
        c.text(cx + 114, hy + 2.5, "ID & Haiart", size=6.0, bold=True, rgb=(0.2, 0.22, 0.28))

        s_list = sorted(sharks_by_row[sid], key=lambda x: x["luecke"])
        step_y = 12.6
        for k, s in enumerate(s_list):
            iy = hy - (k + 1) * step_y
            if k % 2 == 1:
                c.fill_rgb(0.96, 0.97, 0.99)
                c.rect(cx + 2, iy - 1, card_w - 4, step_y, fill=True, stroke=False)

            g = s["luecke"]
            p_l = "S-L" if g == 1 else f"P{g-1:02d}"
            p_r = "S-R" if g == 17 else f"P{g:02d}"

            c.text(cx + 6, iy + 2, f"LED {g:2d}", size=6.0, bold=True, rgb=(0.1, 0.15, 0.25))
            c.text(cx + 28, iy + 2, f"{p_l}/{p_r}", size=5.7, rgb=(0.35, 0.38, 0.42))

            cr, cg, cb = COLOR_MAP[s["farbe"]]
            c.fill_rgb(cr, cg, cb)
            c.rect(cx + 64, iy + 1, 20, 7.5, fill=True, stroke=False)
            ftxt = (0.1, 0.1, 0.1) if s["farbe"] in ("gelb", "orange") else (1, 1, 1)
            c.text(cx + 74, iy + 2.5, s["farbe"][:4], size=5.2, bold=True, rgb=ftxt, align="center")

            c.text(cx + 88, iy + 2, f"{s['depth_m']:.0f}m", size=5.8, rgb=(0.2, 0.22, 0.25))
            sp_short = s["species"].split(" ")[0][0] + ". " + s["species"].split(" ")[1] if " " in s["species"] else s["species"]
            c.text(cx + 114, iy + 2, f"#{s['led_id']} {sp_short[:15]}", size=5.6, rgb=(0.15, 0.18, 0.22))


def write_pdf(path, pages):
    objs = []

    def add_obj(body):
        objs.append(body)
        return len(objs)

    f1 = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    f2 = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    pages_id = add_obj(b"")

    page_ids = []
    for p in pages:
        raw = p.stream_bytes()
        comp = zlib.compress(raw, 9)
        cid = add_obj(f"<< /Length {len(comp)} /Filter /FlateDecode >>\nstream\n".encode("ascii") + comp + b"\nendstream")
        pid = add_obj(
            f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {W_PT:.2f} {H_PT:.2f}] "
            f"/Resources << /Font << /F1 {f1} 0 R /F2 {f2} 0 R >> >> /Contents {cid} 0 R >>".encode("ascii")
        )
        page_ids.append(pid)

    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objs[pages_id - 1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("ascii")
    cat_id = add_obj(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("ascii"))

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out.extend(f"{i} 0 obj\n".encode("ascii"))
        out.extend(body)
        out.extend(b"\nendobj\n")
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer\n<< /Size {len(objs) + 1} /Root {cat_id} 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("ascii")
    )
    path.write_bytes(bytes(out))


def main():
    lr = json.loads((OUT / "led_reihen_3d.json").read_text(encoding="utf-8"))
    d3 = json.loads((OUT / "teile_3d.json").read_text(encoding="utf-8"))
    top_curves = {}
    for p in d3["parts"]:
        if p["kind"] in ("strip", "side"):
            top = []
            for u, z in p["exterior"]:
                if not top or u > top[-1][0]:
                    top.append((u, z))
                else:
                    break
            top_curves[p["id"]] = top

    p0, p1, p2, p3 = Canvas(), Canvas(), Canvas(), Canvas()
    draw_page1_3d_visual(p0, lr, d3, top_curves)
    draw_page1(p1, lr, top_curves)
    draw_page2(p2, lr, top_curves)
    draw_page3(p3, lr)

    pdf_path = OUT / "led_reihen_anleitung.pdf"
    write_pdf(pdf_path, [p0, p1, p2, p3])
    if DELIV.exists():
        shutil.copyfile(pdf_path, DELIV / "00_LED_8_Reihen_Anleitung.pdf")
    print("Wrote 4-page PDF:", pdf_path, pdf_path.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
