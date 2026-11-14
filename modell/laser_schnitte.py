"""Stage 2 of the laser export: build the slice lattice, nest it on 600 x 300 boards, write SVGs.

Run after laser_abtasten.py:
  /opt/anaconda3/bin/python3 modell/laser_schnitte.py [--dicke 2.0] [--schlitz 1.9] [--kerf 0.1]

Construction (decided 2026-11-12):
- model scaled uniformly to 300 mm width (factor 300/279)
- 18 profile slices across x, outer faces flush at x=0 and x=300
  - S-L, S-R: full side plates, floor to surface, tabs into the floor
  - P01..P16: surface strips only (wave line on top, band below)
- Q1..Q5: cross bands along x at LED-free y positions, half-lap with the strips,
  end tabs through the side plates
- B: floor plate with slots for the side plate tabs
- no LED holes; LEDs sit in the gaps between slices (led_montage.csv)

Outputs go to modell/export/laser_v1/.
"""
import argparse
import csv
import json
import math
import os
import random

import numpy as np
import shapely
from shapely import affinity
from shapely.geometry import LineString, Polygon, box
from shapely.ops import polylabel

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "export", "laser_v1")
LED_CSV = os.path.join(HERE, "export", "endmodell_v4", "led_positionen_v4.csv")

# ---- parameters -------------------------------------------------------------
WIDTH = 300.0                 # scaled model width (x)
N_PLATES = 18
BAND = 20.0                   # strip / cross band width, perpendicular to the surface
CROSS_Y = [21.9, 54.9, 95.2, 145.8, 264.8]  # scaled y of the cross bands (LED-free windows)
LED_SIZE = 6.0
MIN_LED_CLEAR = 1.0           # clear air between LED body and cross band face
SIDE_TAB_LEN = 10.0
SIDE_TAB_AT = (0.15, 0.5, 0.85)
FLOOR_MARGIN_X = 6.0
FLOOR_MARGIN_Y = 3.0
BOARD_W, BOARD_H = 600.0, 300.0
BOARD_MARGIN = 5.0
PART_GAP = 3.0
N_BOARDS = 26               # sanity cap only
STROKE_MM = 0.035278         # line width of cut paths in mm (= 0.1 pt)
N_ORDERS = 30                # part orders tried by the nester (fixed seed, reproducible)
GRAIN_FREE = ("floor", "side")  # only full plates may turn 90 deg; bands stay along the grain
RES = 0.5                     # nesting raster in mm
STEP = 0.5                    # curve sampling in mm
TEXT_H = 4.0


# ---- surface ----------------------------------------------------------------
class Surface:
    def __init__(self, path, scale):
        d = np.load(path)
        self.z = d["z"]
        self.step = float(d["step"])
        self.s = scale
        self.ymax = scale * float(d["ys"][-1])

    def h(self, X, Y):
        """Scaled surface height at scaled (X, Y), bilinear."""
        X = np.asarray(X, float) / self.s / self.step
        Y = np.asarray(Y, float) / self.s / self.step
        nx, ny = self.z.shape
        X = np.clip(X, 0, nx - 1.000001)
        Y = np.clip(Y, 0, ny - 1.000001)
        i, j = np.floor(X).astype(int), np.floor(Y).astype(int)
        fx, fy = X - i, Y - j
        z = (self.z[i, j] * (1 - fx) * (1 - fy) + self.z[i + 1, j] * fx * (1 - fy)
             + self.z[i, j + 1] * (1 - fx) * fy + self.z[i + 1, j + 1] * fx * fy)
        return self.s * z


def band_bottom(u, top, band):
    """Lower edge of a band of perpendicular width `band` below the curve (disk erosion)."""
    n = len(u)
    k = int(math.ceil(band / STEP))
    out = np.full(n, np.inf)
    for d in range(-k, k + 1):
        du = d * STEP
        if abs(du) > band:
            continue
        drop = math.sqrt(band * band - du * du)
        lo, hi = max(0, -d), min(n, n - d)
        out[lo:hi] = np.minimum(out[lo:hi], top[lo + d:hi + d] - drop)
    return np.maximum(out, 0.0)


def interp(u, v, at):
    return float(np.interp(at, u, v))


# ---- parts ------------------------------------------------------------------
class Part:
    def __init__(self, pid, kind, poly, place):
        self.pid, self.kind, self.poly, self.place = pid, kind, poly, place
        self.board = None
        self.rot = 0
        self.offset = (0.0, 0.0)


def strip_like(u, top, bot, notches_from_below, tabs_below=()):
    """Polygon from a top curve and a bottom curve over u.
    notches_from_below: list of (u_center, width, z_top) slots cut upward from the bottom edge.
    tabs_below: list of (u_center, length, depth) tabs hanging below a flat bottom (z=0)."""
    pts = [(u[k], top[k]) for k in range(len(u))]
    events = sorted([(c, w, zt, "notch") for c, w, zt in notches_from_below]
                    + [(c, L, dp, "tab") for c, L, dp in tabs_below], key=lambda e: -e[0])
    bottom = []
    cur = u[-1]
    bottom.append((u[-1], bot[-1]))
    for c, w, val, typ in events:
        a, b = c + w / 2, c - w / 2
        mask = (u < cur) & (u > a)
        bottom += [(uu, bb) for uu, bb in zip(u[mask][::-1], bot[mask][::-1])]
        if typ == "notch":
            bottom += [(a, interp(u, bot, a)), (a, val), (b, val), (b, interp(u, bot, b))]
        else:
            bottom += [(a, 0.0), (a, -val), (b, -val), (b, 0.0)]
        cur = b
    mask = u < cur
    bottom += [(uu, bb) for uu, bb in zip(u[mask][::-1], bot[mask][::-1])]
    bottom.append((u[0], bot[0]))
    return Polygon(pts + bottom)


def build(surf, thick, slot):
    ymax = surf.ymax
    pitch = (WIDTH - thick) / (N_PLATES - 1)
    xmid = [k * pitch + thick / 2 for k in range(N_PLATES)]
    uy = np.arange(0.0, ymax + 1e-9, STEP)
    if uy[-1] < ymax:
        uy = np.append(uy, ymax)
    ux = np.arange(thick, WIDTH - thick + 1e-9, STEP)
    if ux[-1] < WIDTH - thick:
        ux = np.append(ux, WIDTH - thick)

    # cross band curves (body between the side plates)
    cross = []
    for j, yc in enumerate(CROSS_Y):
        top = surf.h(ux, np.full_like(ux, yc))
        cross.append((yc, top, band_bottom(ux, top, BAND)))

    joints = []
    parts = []
    # profile slices
    for k, xm in enumerate(xmid):
        top = surf.h(np.full_like(uy, xm), uy)
        if k in (0, N_PLATES - 1):
            pid = "S-L" if k == 0 else "S-R"
            bot = np.zeros_like(uy)
            tabs = [(f * ymax, SIDE_TAB_LEN, thick) for f in SIDE_TAB_AT]
            poly = strip_like(uy, top, bot, [], tabs)
            holes = []
            for yc, ctop, cbot in cross:
                end = 0 if k == 0 else -1
                ht, hb = ctop[end], cbot[end]
                q = (ht - hb) / 4
                holes.append(box(yc - slot / 2, hb + q, yc + slot / 2, ht - q))
            poly = poly.difference(shapely.union_all(holes))
            parts.append(Part(pid, "side", poly, {"axis": "x", "at": xm - thick / 2}))
        else:
            pid = f"P{k:02d}"
            bot = band_bottom(uy, top, BAND)
            notches = []
            for j, (yc, ctop, cbot) in enumerate(cross):
                t = float(surf.h(xm, yc))
                low = max(interp(uy, bot, yc), interp(ux, cbot, xm))
                mid = (t + low) / 2
                joints.append({"strip": pid, "band": f"Q{j + 1}", "top": t, "low": low, "mid": mid,
                               "overlap": t - low})
                notches.append((yc, slot, mid))
            poly = strip_like(uy, top, bot, notches)
            parts.append(Part(pid, "strip", poly, {"axis": "x", "at": xm - thick / 2}))

    # cross bands: slots from above at every strip, tabs through the side plates
    for j, (yc, top, bot) in enumerate(cross):
        pid = f"Q{j + 1}"
        u = np.concatenate([[0.0], ux, [WIDTH]])
        t = np.concatenate([[top[0]], top, [top[-1]]])
        b = np.concatenate([[bot[0]], bot, [bot[-1]]])
        body = strip_like(ux, top, bot, [])
        ql, qr = (top[0] - bot[0]) / 4, (top[-1] - bot[-1]) / 4
        tabl = box(0.0, bot[0] + ql, thick, top[0] - ql)
        tabr = box(WIDTH - thick, bot[-1] + qr, WIDTH, top[-1] - qr)
        poly = shapely.union_all([body, tabl, tabr])
        cuts = []
        for jt in joints:
            if jt["band"] != pid:
                continue
            k = int(jt["strip"][1:])
            xm = xmid[k]
            cuts.append(box(xm - slot / 2, jt["mid"], xm + slot / 2, max(t.max(), jt["top"]) + 5))
        poly = poly.difference(shapely.union_all(cuts))
        parts.append(Part(pid, "cross", poly, {"axis": "y", "at": yc - thick / 2}))
        del u, b

    # floor
    fl = box(-FLOOR_MARGIN_X, -FLOOR_MARGIN_Y, WIDTH + FLOOR_MARGIN_X, ymax + FLOOR_MARGIN_Y)
    holes = []
    for xm in (xmid[0], xmid[-1]):
        for f in SIDE_TAB_AT:
            yc = f * ymax
            holes.append(box(xm - slot / 2, yc - SIDE_TAB_LEN / 2, xm + slot / 2, yc + SIDE_TAB_LEN / 2))
    fl = fl.difference(shapely.union_all(holes))
    parts.append(Part("B", "floor", fl, {"axis": "z", "at": -thick}))
    return parts, joints, xmid, pitch


# ---- stroke font for engraving ----------------------------------------------
# glyphs on a 2 x 4 grid (x 0..2, y 0..4), each a list of polylines
GLYPHS = {
    "0": [[(0, 0), (2, 0), (2, 4), (0, 4), (0, 0)]],
    "1": [[(1, 0), (1, 4), (0.4, 3.4)]],
    "2": [[(0, 4), (2, 4), (2, 2), (0, 2), (0, 0), (2, 0)]],
    "3": [[(0, 4), (2, 4), (2, 0), (0, 0)], [(0.5, 2), (2, 2)]],
    "4": [[(0, 4), (0, 2), (2, 2)], [(2, 4), (2, 0)]],
    "5": [[(2, 4), (0, 4), (0, 2), (2, 2), (2, 0), (0, 0)]],
    "6": [[(2, 4), (0, 4), (0, 0), (2, 0), (2, 2), (0, 2)]],
    "7": [[(0, 4), (2, 4), (2, 0)]],
    "8": [[(0, 0), (2, 0), (2, 4), (0, 4), (0, 0)], [(0, 2), (2, 2)]],
    "9": [[(0, 0), (2, 0), (2, 4), (0, 4), (0, 2), (2, 2)]],
    "P": [[(0, 0), (0, 4), (2, 4), (2, 2), (0, 2)]],
    "Q": [[(0, 0), (2, 0), (2, 4), (0, 4), (0, 0)], [(1.2, 0.8), (2.4, -0.4)]],
    "S": [[(2, 4), (0, 4), (0, 2), (2, 2), (2, 0), (0, 0)]],
    "L": [[(0, 4), (0, 0), (2, 0)]],
    "R": [[(0, 0), (0, 4), (2, 4), (2, 2), (0, 2), (2, 0)]],
    "B": [[(0, 0), (0, 4), (1.6, 4), (2, 3.4), (1.6, 2), (0, 2)], [(1.6, 2), (2, 1.2), (2, 0.6), (1.6, 0), (0, 0)]],
    "-": [[(0.3, 2), (1.7, 2)]],
    ">": [[(0, 4), (2, 2), (0, 0)]],
}


def text_lines(s, h):
    sc = h / 4.0
    adv = 3.0 * sc
    lines = []
    for n, ch in enumerate(s):
        for pl in GLYPHS.get(ch, []):
            lines.append([(n * adv + x * sc, y * sc) for x, y in pl])
    return lines, len(s) * adv - sc


def label_for(part):
    """Place the part ID (plus an arrow toward the coast on profile parts) inside the part."""
    s = part.pid + (" >" if part.kind in ("strip", "side") else "")
    s = s.replace(" ", "")
    inner = part.poly.buffer(-1.0)
    for h in (TEXT_H, 3.0, 2.0):
        lines, w = text_lines(s, h)
        minx, miny, maxx, maxy = inner.bounds
        cand = []
        for x in np.arange(minx, maxx - w, 2.0):
            for y in np.arange(miny, maxy - h, 1.0):
                cand.append((x, y))
        # prefer positions toward the middle of the part
        cx, cy = inner.centroid.x, inner.centroid.y
        cand.sort(key=lambda p: (p[0] + w / 2 - cx) ** 2 + (p[1] + h / 2 - cy) ** 2)
        for x, y in cand:
            if inner.contains(box(x - 0.5, y - 0.8, x + w + 0.5, y + h + 0.5)):
                return [[(x + a, y + b) for a, b in pl] for pl in lines]
    p = polylabel(inner, 0.5) if not inner.is_empty else part.poly.representative_point()
    lines, w = text_lines(s, 2.0)
    return [[(p.x - w / 2 + a, p.y - 1 + b) for a, b in pl] for pl in lines]


# ---- nesting ----------------------------------------------------------------
def raster(poly, res):
    # a cell is occupied if the part touches it, so the whole part lies inside the marked cells.
    # Cells whose centre is more than half a diagonal inside or outside are decided by the
    # centre; only the band along the outline gets an exact cell/part intersection test.
    minx, miny, maxx, maxy = poly.bounds
    nx = int(math.ceil((maxx - minx) / res - 1e-9))
    ny = int(math.ceil((maxy - miny) / res - 1e-9))
    xs = minx + res * np.arange(nx)
    ys = miny + res * np.arange(ny)
    gx, gy = np.meshgrid(xs + res / 2, ys + res / 2)
    h = res * 0.7072
    m = shapely.contains_xy(poly.buffer(-h), gx, gy)
    iy, ix = np.nonzero(shapely.contains_xy(poly.buffer(h), gx, gy) & ~m)
    shapely.prepare(poly)
    m[iy, ix] = shapely.intersects(poly, shapely.box(xs[ix], ys[iy], xs[ix] + res, ys[iy] + res))
    return m, (minx, miny)


def dilate(m, r):
    rr = int(math.ceil(r))
    h, w = m.shape
    out = np.zeros((h + 2 * rr, w + 2 * rr), bool)
    for dy in range(-rr, rr + 1):
        for dx in range(-rr, rr + 1):
            if dx * dx + dy * dy <= r * r:
                out[rr + dy:rr + dy + h, rr + dx:rr + dx + w] |= m
    return out, rr


def _fit(occ, m, d, rr, uw, uh):
    """Bottom-left valid position (column, row) of mask m with gap mask d on board occ, or None.

    Rows run with y up (row 0 = bottom edge). Packing bottom-left and compacting toward the
    top-left afterwards (_compact) needed 5 boards; packing top-left directly needed 6.
    """
    big = np.zeros((uh + 2 * rr, uw + 2 * rr), bool)
    big[rr:rr + uh, rr:rr + uw] = occ
    H, W = big.shape
    h, w = d.shape
    F = np.fft.rfft2(big.astype(float))
    K = np.fft.rfft2(d[::-1, ::-1].astype(float), s=(H, W))
    corr = np.fft.irfft2(F * K, s=(H, W))
    # corr[r + h - 1, c + w - 1] = overlap when d's top-left sits at (r, c) in big;
    # the core mask m must stay inside the usable area
    valid = (corr[h - 1:, w - 1:] < 0.5)[:uh - m.shape[0] + 1, :uw - m.shape[1] + 1]
    if not valid.any():
        return None
    rs, cs = np.nonzero(valid)
    k = np.lexsort((rs, cs))[0]  # leftmost column, then lowest row
    return int(cs[k]), int(rs[k])


def _pack(order, masks, uw, uh):
    boards, where = [], {}
    for pid in order:
        best = None
        for rot, (m, d, rr, ox, oy) in masks[pid].items():
            for bi, occ in enumerate(boards + [np.zeros((uh, uw), bool)]):
                pos = _fit(occ, m, d, rr, uw, uh)
                if pos:
                    cand = (bi, pos[0], pos[1])
                    if best is None or cand < best[0]:
                        best = (cand, rot, pos)
                    break
        if best is None:
            raise SystemExit(f"part {pid} does not fit on a board")
        (bi, _, _), rot, (c, r) = best
        if bi == len(boards):
            boards.append(np.zeros((uh, uw), bool))
        m = masks[pid][rot][0]
        boards[bi][r:r + m.shape[0], c:c + m.shape[1]] |= m
        where[pid] = (bi, rot, c, r)
    return len(boards), where


def _compact(where, masks, uw, uh):
    """Push every part up, then left, as far as it goes; repeat until nothing moves.

    Keeps the PART_GAP clearance (same dilated masks as packing). Returns the used board
    length in raster cells (sum over boards), the measure for the free offcut at the right.
    """
    where = dict(where)
    n = max(b for b, *_ in where.values()) + 1

    def free(pid, c, r, others):
        m, d, rr = masks[pid][where[pid][1]][:3]
        if c < 0 or r < 0 or c + m.shape[1] > uw or r + m.shape[0] > uh:
            return False
        return not (others[r:r + d.shape[0], c:c + d.shape[1]] & d).any()

    for bi in range(n):
        ids = [k for k, v in where.items() if v[0] == bi]
        moved = True
        while moved:
            moved = False
            for axis in ("up", "left"):
                key = (lambda k: -(where[k][3] + masks[k][where[k][1]][0].shape[0])) if axis == "up" \
                    else (lambda k: where[k][2])
                for pid in sorted(ids, key=key):
                    rr = masks[pid][where[pid][1]][2]
                    others = np.zeros((uh + 2 * rr, uw + 2 * rr), bool)
                    for o in ids:
                        if o != pid:
                            _, ro, co, rw = where[o]
                            mo = masks[o][ro][0]
                            others[rr + rw:rr + rw + mo.shape[0], rr + co:rr + co + mo.shape[1]] |= mo
                    b, rot, c, r = where[pid]
                    dc, dr = (0, 1) if axis == "up" else (-1, 0)
                    step = 64
                    while step:
                        if free(pid, c + dc * step, r + dr * step, others):
                            c, r = c + dc * step, r + dr * step
                            moved = True
                        else:
                            step //= 2
                    where[pid] = (b, rot, c, r)
    used = 0
    for bi in range(n):
        used += max(where[k][2] + masks[k][where[k][1]][0].shape[1] for k, v in where.items() if v[0] == bi)
    return used, where


def nest(parts, kerf):
    """Pack parts on as few boards as possible, starting top-left; the free offcut stays at the right.

    Tries N_ORDERS part orders (floor and side plates first, the rest shuffled with a fixed
    seed), keeps the layouts with the fewest boards, compacts them toward the top-left and
    takes the one with the shortest used board length.
    """
    # every part is grown by half the part gap, so its grown shape may come PART_GAP / 2
    # closer to the board edge than the margin
    edge = BOARD_MARGIN - PART_GAP / 2
    uw = int(round((BOARD_W - 2 * edge) / RES))
    uh = int(round((BOARD_H - 2 * edge) / RES))
    masks = {}
    for p in parts:
        masks[p.pid] = {}
        for rot in ((0, 90, 180, 270) if p.kind in GRAIN_FREE else (0, 180)):
            cut = p.poly.buffer(kerf / 2, join_style="mitre")
            g = affinity.rotate(cut.buffer(PART_GAP / 2), rot, origin=(0, 0))
            m, (ox, oy) = raster(g, RES)
            if m.shape[0] > uh or m.shape[1] > uw:
                continue
            # the mask covers every cell the grown part touches; masks that do not overlap
            # keep the cut outlines at least PART_GAP apart, so no extra dilation is needed
            d, rr = dilate(m, 0)
            masks[p.pid][rot] = (m, d, rr, ox, oy)
        if not masks[p.pid]:
            raise SystemExit(f"part {p.pid} does not fit on a board")
    by_id = {p.pid: p for p in parts}
    base = sorted(by_id, key=lambda k: (by_id[k].kind != "floor", by_id[k].kind != "side", -by_id[k].poly.area))
    fixed = [k for k in base if by_id[k].kind in GRAIN_FREE]
    rest = [k for k in base if k not in fixed]
    rng = random.Random(1)
    orders = [base]
    for _ in range(N_ORDERS - 1):
        r = rest[:]
        rng.shuffle(r)
        orders.append(fixed + r)
    packed = [_pack(o, masks, uw, uh) for o in orders]
    n = min(k for k, _ in packed)
    used, where = min((_compact(w, masks, uw, uh) for k, w in packed if k == n), key=lambda t: t[0])
    for pid, (bi, rot, c, r) in where.items():
        p = by_id[pid]
        ox, oy = masks[pid][rot][3:]
        p.board, p.rot = bi, rot
        # board coordinates (mm, y up, origin at the bottom-left board corner)
        p.offset = (edge + c * RES - ox, edge + r * RES - oy)
    if n > N_BOARDS:
        raise SystemExit(f"needs {n} boards, cap is {N_BOARDS}")
    return n


def to_board(geom, p):
    g = affinity.rotate(geom, p.rot, origin=(0, 0))
    return affinity.translate(g, p.offset[0], p.offset[1])


def lines_to_board(lines, p):
    out = []
    for pl in lines:
        ls = to_board(LineString(pl), p)
        out.append(list(ls.coords))
    return out


# ---- svg --------------------------------------------------------------------
def path_d(coords):
    pts = [(x, BOARD_H - y) for x, y in coords]
    return "M " + " L ".join(f"{x:.3f},{y:.3f}" for x, y in pts)


def poly_paths(g):
    geoms = getattr(g, "geoms", [g])
    out = []
    for pg in geoms:
        out.append(path_d(pg.exterior.coords) + " Z")
        for r in pg.interiors:
            out.append(path_d(r.coords) + " Z")
    return out


def write_svg(path, cut_paths, engrave_lines, title):
    with open(path, "w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(f'<svg xmlns="http://www.w3.org/2000/svg" width="{BOARD_W}mm" height="{BOARD_H}mm" '
                f'viewBox="0 0 {BOARD_W} {BOARD_H}">\n<title>{title}</title>\n')
        if engrave_lines:
            f.write(f'<g id="gravur" fill="none" stroke="#0000ff" stroke-width="{STROKE_MM}">\n')
            for pl in engrave_lines:
                f.write(f'<path d="{path_d(pl)}"/>\n')
            f.write("</g>\n")
        f.write(f'<g id="schnitt" fill="none" stroke="#ff0000" stroke-width="{STROKE_MM}">\n')
        for d in cut_paths:
            f.write(f'<path d="{d}"/>\n')
        f.write("</g>\n</svg>\n")


def test_strip(kerf, path):
    widths = [1.7, 1.8, 1.9, 2.0, 2.1, 2.2]
    W, H, depth = 20.0 + 14.0 * len(widths), 25.0, 10.0
    poly = box(0, 0, W, H)
    cuts = []
    for n, w in enumerate(widths):
        cx = 17.0 + 14.0 * n
        cuts.append(box(cx - w / 2, H - depth, cx + w / 2, H + 1))
    poly = poly.difference(shapely.union_all(cuts)).buffer(kerf / 2, join_style="mitre")
    off = (BOARD_MARGIN, BOARD_H - BOARD_MARGIN - H)  # top-left corner
    poly = affinity.translate(poly, *off)
    write_svg(path, poly_paths(poly), (), "Schlitz-Testleiste 1.7 bis 2.2 mm")
    return widths


# ---- leds -------------------------------------------------------------------
def led_map(scale, xmid, pitch, thick, surf):
    rows = list(csv.DictReader(open(LED_CSV, encoding="utf-8")))
    names = ["S-L"] + [f"P{k:02d}" for k in range(1, N_PLATES - 1)] + ["S-R"]
    gap_c = [xmid[k] + pitch / 2 for k in range(N_PLATES - 1)]
    out = []
    for r in rows:
        x, y = scale * float(r["x_mm"]), scale * float(r["y_mm"])
        g = int(np.argmin([abs(x - c) for c in gap_c]))
        dists = [abs(y - yc) for yc in CROSS_Y]
        jb = int(np.argmin(dists))
        clear = dists[jb] - thick / 2 - LED_SIZE / 2
        out.append({
            "led_id": r["led_id"], "species": r["species"], "farbe": r["farbe"],
            "ansteuerung": r["ansteuerung"], "depth_m": r["depth_m"],
            "luecke": g + 1, "zwischen": f"{names[g]} / {names[g + 1]}",
            "x_mm": round(gap_c[g], 2), "y_mm": round(y, 2),
            "z_oberflaeche_mm": round(float(surf.h(gap_c[g], y)), 2),
            "verschiebung_x_mm": round(gap_c[g] - x, 2),
            "naechstes_querband": f"Q{jb + 1}", "luft_zum_querband_mm": round(clear, 2),
        })
    return out


# ---- main -------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dicke", type=float, default=2.0, help="measured board thickness in mm")
    ap.add_argument("--schlitz", type=float, default=None, help="slot width in mm (default dicke - 0.1)")
    ap.add_argument("--kerf", type=float, default=0.1, help="laser kerf in mm")
    a = ap.parse_args()
    thick = a.dicke
    slot = a.schlitz if a.schlitz is not None else round(thick - 0.1, 3)
    kerf = a.kerf

    npz = np.load(os.path.join(OUT, "oberflaeche_05mm.npz"))
    scale = WIDTH / float(npz["xs"][-1])
    surf = Surface(os.path.join(OUT, "oberflaeche_05mm.npz"), scale)
    parts, joints, xmid, pitch = build(surf, thick, slot)

    checks = {}
    bad = [p.pid for p in parts if not p.poly.is_valid or p.poly.geom_type != "Polygon"]
    checks["polygone_gueltig_einteilig"] = not bad
    assert not bad, f"invalid or split parts: {bad}"
    min_ov = min(j["overlap"] for j in joints)
    checks["min_ueberlappung_streifen_querband_mm"] = round(min_ov, 2)
    assert min_ov >= 8.0, f"joint overlap too small: {min_ov:.2f} mm"

    n_boards = nest(parts, kerf)
    checks["bretter_benutzt"] = n_boards

    leds = led_map(scale, xmid, pitch, thick, surf)
    min_clear = min(l["luft_zum_querband_mm"] for l in leds)
    checks["leds_zugeordnet"] = len(leds)
    checks["min_luft_led_querband_mm"] = min_clear
    assert len(leds) == 109, len(leds)
    assert min_clear >= MIN_LED_CLEAR, f"LED too close to a cross band: {min_clear} mm"

    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        if f.startswith("brett_") and f.endswith(".svg"):
            os.remove(os.path.join(OUT, f))
    usable = box(BOARD_MARGIN, BOARD_MARGIN, BOARD_W - BOARD_MARGIN, BOARD_H - BOARD_MARGIN)
    board_rows, part_rows = [], []
    for bi in range(n_boards):
        cut, length = [], 0.0
        for p in [p for p in parts if p.board == bi]:
            g = to_board(p.poly.buffer(kerf / 2, join_style="mitre"), p)
            assert usable.buffer(0.01).contains(g), f"{p.pid} leaves the usable board area"
            cut += poly_paths(g)
            length += g.length
        write_svg(os.path.join(OUT, f"brett_{bi + 1:02d}.svg"), cut, (), f"Brett {bi + 1:02d}")
        board_rows.append({"brett": bi + 1, "teile": [p.pid for p in parts if p.board == bi],
                           "schnittlaenge_mm": round(length, 1)})
    for p in sorted(parts, key=lambda p: p.pid):
        minx, miny, maxx, maxy = p.poly.bounds
        part_rows.append({"teil": p.pid, "art": p.kind, "brett": p.board + 1,
                          "breite_mm": round(maxx - minx, 1), "hoehe_mm": round(maxy - miny, 1),
                          "flaeche_cm2": round(p.poly.area / 100, 1),
                          "schlitze_und_loecher": len(p.poly.interiors) + sum(
                              1 for j in joints if j["strip"] == p.pid or j["band"] == p.pid)})

    with open(os.path.join(OUT, "teileliste.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(part_rows[0]))
        w.writeheader()
        w.writerows(part_rows)
    with open(os.path.join(OUT, "led_montage.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(leds[0]))
        w.writeheader()
        w.writerows(leds)
    widths = test_strip(kerf, os.path.join(OUT, "schlitz_testleiste.svg"))

    # true-size geometry with 3D placement for the reassembly scene
    with open(os.path.join(OUT, "teile_3d.json"), "w") as f:
        json.dump({"dicke": thick, "parts": [
            {"id": p.pid, "kind": p.kind, "place": p.place,
             "exterior": [list(c) for c in p.poly.exterior.coords],
             "holes": [[list(c) for c in r.coords] for r in p.poly.interiors]} for p in parts],
            "leds": leds}, f)

    shifts = [abs(l["verschiebung_x_mm"]) for l in leds]
    metrics = {
        "datum": "2026-11-12",
        "quelle": "hang_sagami_endmodell_v4_mit_waenden.blend / Hang_Endmodell_Druck",
        "skalierung": round(scale, 5),
        "modell_mm": [WIDTH, round(surf.ymax, 1), round(float(surf.z.max()) * scale, 1)],
        "tiefe_massstab": f"1 cm = {round(135 / scale, 1)} m",
        "plattendicke_mm": thick, "schlitzbreite_mm": slot, "kerf_mm": kerf,
        "scheiben": N_PLATES, "abstand_mitte_mm": round(pitch, 3),
        "luft_zwischen_scheiben_mm": round(pitch - thick, 3),
        "bandbreite_mm": BAND, "querbaender_y_mm": CROSS_Y,
        "led_verschiebung_x_mm": {"median": round(float(np.median(shifts)), 2), "max": round(max(shifts), 2)},
        "testleiste_schlitze_mm": widths,
        "bretter": board_rows, "checks": checks,
        "gesamt_schnittlaenge_m": round(sum(b["schnittlaenge_mm"] for b in board_rows) / 1000, 2),
    }
    with open(os.path.join(OUT, "metriken_laser.json"), "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: metrics[k] for k in ("skalierung", "modell_mm", "tiefe_massstab",
                                              "abstand_mitte_mm", "luft_zwischen_scheiben_mm",
                                              "led_verschiebung_x_mm", "checks", "gesamt_schnittlaenge_m")},
                     ensure_ascii=False))
    for b in board_rows:
        print(f"Brett {b['brett']:02d}: {', '.join(b['teile'])}  ({b['schnittlaenge_mm'] / 1000:.2f} m)")


if __name__ == "__main__":
    main()
