"""Build the support-free printable Sagami slope model (pure 3 mm slope shell without side walls, standing on edge at z=0).

Run from the repository root:
  /Applications/Blender.app/Contents/MacOS/Blender -b modell/hang_sagami_final.blend --python modell/baue_endmodell_v4.py
"""
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "modell"
OUT = MODEL / "export" / "endmodell_v4"
OUT.mkdir(parents=True, exist_ok=True)

GRID = ROOT / "data/raw/bathymetrie/sagami_grid.csv"
PROFILE = ROOT / "data/processed/sagami_profil.csv"
LAND = ROOT / "data/processed/sagami_land.csv"
OLD_CSV = MODEL / "export/led_positionen.csv"
NEW_CSV = OUT / "led_positionen_v4.csv"
HOLE_CSV = OUT / "loch_positionen_v4.csv"
NEW_BLEND = MODEL / "hang_sagami_endmodell_v4.blend"
NEW_STL = OUT / "hang_sagami_endmodell_v4_druck.stl"
NEW_STL_AUSSTELLUNG = OUT / "hang_sagami_endmodell_v4_ausstellung.stl"

# Dimensions: 10% smaller than the 310 x 290 x 280.84 mm model (279 x 261 x 252.4 mm),
# 6.0 x 6.0 mm LED holes and 3.0 mm wall thickness, pure slope shell without side walls.
WIDTH_OLD, DEPTH_OLD, Y_COAST_OLD = 340.0, 315.0, 280.0
WIDTH, DEPTH = 279.0, 261.0
SCALE_XY = DEPTH / DEPTH_OLD
Y_COAST = round(Y_COAST_OLD * SCALE_XY, 1)  # 232.0 mm
STEP = 0.5

MAX_DEPTH = 1305.0
MM_PER_M = (10.0 / 45.0) * SCALE_XY
BASE = 5.0 * SCALE_XY
Z0 = BASE + MAX_DEPTH * MM_PER_M

WALL = 3.0
T_ERODE = 3.1
HOLE = 6.0
HOLE_OUT, HOLE_IN = 4.0, 7.5
RAY0 = HOLE_OUT + 2.0
MIN_GAP = 12.0
MARGIN_X = 11.0  # keeps all 6x6 mm normal holes >= 8 mm away from the standing edge x=0 and top edge x=WIDTH
PLA = 1.24

XS = np.arange(0.0, WIDTH + 1e-6, STEP)
YS = np.arange(0.0, DEPTH + 1e-6, STEP)
NX, NY = len(XS), len(YS)
GX, GY = np.meshgrid(XS, YS)
SEA = GY < Y_COAST

with open(PROFILE, newline="") as f:
    prof = list(csv.DictReader(f))
KM = np.array([float(r["km"]) for r in prof])
DEP = np.array([float(r["depth_m"]) for r in prof])
KM_END, P_LAT, P_LON = KM[-1], float(prof[0]["lat"]), float(prof[0]["lon"])
MM_PER_KM = Y_COAST / KM_END
KM_PER_DEG_LAT = 111.0
KM_PER_DEG_LON = 111.0 * math.cos(math.radians(P_LAT))
with open(LAND, newline="") as f:
    land = [(float(r["km_inland"]), float(r["elev_m"])) for r in csv.DictReader(f)]
L_KM = np.array([p[0] for p in land])
L_EL = np.array([p[1] for p in land])


def profile_z(y):
    y = np.asarray(y, dtype=float)
    sea_y = Y_COAST - KM / KM_END * Y_COAST
    z_sea = np.interp(y, sea_y[::-1], (Z0 - DEP * MM_PER_M)[::-1])
    z_land = Z0 + np.interp((y - Y_COAST) / MM_PER_KM, L_KM, L_EL) * MM_PER_M
    return np.where(y < Y_COAST, z_sea, z_land)


rows = [tuple(map(float, ln.split(","))) for ln in GRID.read_text().splitlines()[2:] if ln.strip()]
LATS = np.array(sorted({r[0] for r in rows}, reverse=True))
LONS = np.array(sorted({r[1] for r in rows}))
raw = {(r[0], r[1]): r[2] for r in rows}
ZG = np.array([[raw[(a, b)] for b in LONS] for a in LATS])
D_LAT, D_LON = LATS[0] - LATS[1], LONS[1] - LONS[0]


def coast_lat_per_col():
    out = []
    for j in range(len(LONS)):
        col = ZG[:, j]
        idx = [i for i in range(len(LATS) - 1)
               if 35.2 < LATS[i] < 35.4 and col[i] > 0 >= col[i + 1]]
        i = max(idx) if idx else None
        out.append(np.nan if i is None else LATS[i] - col[i] / (col[i] - col[i + 1]) * D_LAT)
    c = np.array(out)
    ok = ~np.isnan(c)
    c = np.interp(np.arange(len(c)), np.where(ok)[0], c[ok])
    return np.convolve(np.pad(c, 1, mode="edge"), np.ones(3) / 3, mode="valid")


COAST = coast_lat_per_col()


def sample_grid(lat, lon):
    fi = np.clip((LATS[0] - lat) / D_LAT, 0, len(LATS) - 1.001)
    fj = np.clip((lon - LONS[0]) / D_LON, 0, len(LONS) - 1.001)
    i, j = fi.astype(int), fj.astype(int)
    ti, tj = fi - i, fj - j
    return (ZG[i, j] * (1 - ti) * (1 - tj) + ZG[i + 1, j] * ti * (1 - tj)
            + ZG[i, j + 1] * (1 - ti) * tj + ZG[i + 1, j + 1] * ti * tj)


def blur(a, sigma_mm):
    s = sigma_mm / STEP
    r = int(3 * s)
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / s) ** 2)
    k /= k.sum()
    for ax in (0, 1):
        p = np.pad(a, [(r, r) if i == ax else (0, 0) for i in range(2)], mode="edge")
        a = sum(w * np.take(p, np.arange(o, o + a.shape[ax]), axis=ax) for o, w in enumerate(k))
    return a


def relief_depth():
    lon = P_LON + (GX - WIDTH / 2) / MM_PER_KM / KM_PER_DEG_LON
    coast = np.interp(lon, LONS, COAST)
    lat = coast - (Y_COAST - GY) / MM_PER_KM / KM_PER_DEG_LAT
    d = -sample_grid(lat, lon)
    d = blur(np.where(SEA, d, 0.0), 4.0 * SCALE_XY)
    d = np.clip(d, 0.0, MAX_DEPTH)
    d[~SEA] = 0.0
    d[np.isclose(GY, Y_COAST)] = 0.0
    return d


def relief_lesbar(d_rel, d_prof, strength=0.5):
    d = np.clip(d_prof + strength * (d_rel - d_prof), 0.0, MAX_DEPTH)
    d[~SEA] = 0.0
    d = np.maximum.accumulate(d[::-1], axis=0)[::-1]
    d = blur(d, 3.0 * SCALE_XY)
    d[~SEA] = 0.0
    d = np.maximum.accumulate(d[::-1], axis=0)[::-1]
    # Bound lateral gradient along X so that when the 3 mm shell stands on X=0 (Z_print = X),
    # the surface overhang angle from vertical never exceeds 35 degrees anywhere (0 g support).
    max_step_m = (0.70 * STEP) / MM_PER_M
    for _ in range(3):
        for i in range(1, NX):
            d[:, i] = np.clip(d[:, i], d[:, i - 1] - max_step_m, d[:, i - 1] + max_step_m)
        for i in range(NX - 2, -1, -1):
            d[:, i] = np.clip(d[:, i], d[:, i + 1] - max_step_m, d[:, i + 1] + max_step_m)
        d = blur(d, 2.0 * SCALE_XY)
        d[~SEA] = 0.0
        d = np.maximum.accumulate(d[::-1], axis=0)[::-1]
    return d


def surf(x, y):
    fx, fy = x / STEP, y / STEP
    i, j = min(int(fx), NX - 2), min(int(fy), NY - 2)
    tx, ty = fx - i, fy - j
    return float(H[j, i] * (1 - tx) * (1 - ty) + H[j, i + 1] * tx * (1 - ty)
                 + H[j + 1, i] * (1 - tx) * ty + H[j + 1, i + 1] * tx * ty)


Z_PROF = np.broadcast_to(profile_z(YS)[:, None], (NY, NX)).copy()
D_PROF = np.where(SEA, (Z0 - Z_PROF) / MM_PER_M, 0.0)
D_REL = relief_depth()
D_SMOOTH = relief_lesbar(D_REL, D_PROF, 0.5)
H = np.where(SEA, Z0 - D_SMOOTH * MM_PER_M, Z_PROF)
assert np.all(D_SMOOTH[:-1] >= D_SMOOTH[1:] - 1e-9)

# Cavity ceiling by spherical erosion (3.0 mm normal thickness everywhere)
erode_r = int(math.ceil(T_ERODE / STEP))
pad = np.pad(H, erode_r, constant_values=np.inf)
G = np.full_like(H, np.inf)
for dv in range(-erode_r, erode_r + 1):
    for du in range(-erode_r, erode_r + 1):
        d2 = (du * STEP) ** 2 + (dv * STEP) ** 2
        if d2 <= T_ERODE ** 2:
            G = np.minimum(G, pad[erode_r + dv: erode_r + dv + NY, erode_r + du: erode_r + du + NX]
                           - math.sqrt(T_ERODE ** 2 - d2))
hy, hx = np.gradient(H, STEP)


def grid_normal(x, y):
    i, j = int(round(x / STEP)), int(round(y / STEP))
    n = np.array([-hx[j, i], -hy[j, i], 1.0])
    return n / np.linalg.norm(n)


# Verify maximum overhang angle when standing on X=0
normals_grid = np.dstack([-hx, -hy, np.ones_like(H)])
normals_grid /= np.linalg.norm(normals_grid, axis=2, keepdims=True)
max_overhang_x_deg = float(np.degrees(np.arcsin(np.abs(normals_grid[:, :, 0]))).max())
assert max_overhang_x_deg <= 36.0, f"Overhang too steep: {max_overhang_x_deg}"

# Replace source surface mesh
old_body = bpy.data.objects.get("Hang_Endmodell")
if old_body:
    bpy.data.objects.remove(old_body, do_unlink=True)
verts_top = np.column_stack([GX.ravel(), GY.ravel(), H.ravel()])
faces_top = []
for j in range(NY - 1):
    a = j * NX + np.arange(NX - 1)
    faces_top.extend(np.column_stack([a, a + 1, a + NX + 1, a + NX]).tolist())
me_src = bpy.data.meshes.new("Hang_Endmodell_Glatt_Quelle")
me_src.from_pydata(verts_top.tolist(), [], faces_top)
me_src.update()
body = bpy.data.objects.new("Hang_Endmodell", me_src)
coll = bpy.data.collections.get("Endmodell") or bpy.context.scene.collection
coll.objects.link(body)
if "PLA_weiss" in bpy.data.materials:
    me_src.materials.append(bpy.data.materials["PLA_weiss"])

# Place 109 LEDs on scaled relief
with open(OLD_CSV, newline="") as f:
    old_leds = list(csv.DictReader(f))
assert len(old_leds) == 109
old_leds.sort(key=lambda r: (float(r["depth_m"]), int(r["led_id"])))
ix_min = int(math.ceil(MARGIN_X / STEP))
ix_max = NX - 1 - ix_min
placed = []
for r in old_leds:
    x_old, depth = float(r["x_mm"]), float(r["depth_m"])
    x_scaled = MARGIN_X + (x_old - 15.0) / (325.0 - 15.0) * (WIDTH - 2 * MARGIN_X)
    ix0, hit = int(round(x_scaled / STEP)), None
    for k in range(NX):
        for ix in ((ix0 + k, ix0 - k) if k else (ix0,)):
            if not ix_min <= ix <= ix_max:
                continue
            col = D_SMOOTH[:, ix][::-1]
            start = int(round((DEPTH - Y_COAST) / STEP))
            jj = next((q for q in range(start, NY) if col[q] >= depth), None)
            if jj is None:
                continue
            if jj == start:
                y = Y_COAST
            else:
                a, b = col[jj - 1], col[jj]
                t = 0.0 if b == a else (depth - a) / (b - a)
                y = DEPTH - (jj - 1 + t) * STEP
            p = np.array([XS[ix], y, Z0 - depth * MM_PER_M])
            if all(np.linalg.norm(p - q["p"]) >= MIN_GAP for q in placed):
                hit = {"row": r, "p": p}
                break
        if hit:
            break
    assert hit is not None, r["led_id"]
    placed.append(hit)

header = ["led_id", "species", "category", "farbe", "ansteuerung", "depth_m",
          "x_mm", "y_mm", "z_mm", "nx", "ny", "nz"]
led_objects = {}
for obj in bpy.data.objects:
    if obj.name.startswith("LED_"):
        try:
            led_objects[int(obj.name.split("_")[1])] = obj
        except (ValueError, IndexError):
            pass
new_rows = []
for item in placed:
    r, p = item["row"], item["p"]
    n = grid_normal(p[0], p[1])
    new_rows.append([int(r["led_id"]), r["species"], r["category"], r["farbe"], r["ansteuerung"], r["depth_m"],
                     round(p[0], 3), round(p[1], 3), round(p[2], 3),
                     round(n[0], 6), round(n[1], 6), round(n[2], 6)])
    obj = led_objects.get(int(r["led_id"]))
    if obj:
        obj.location = p
new_rows.sort(key=lambda r: r[0])
with open(NEW_CSV, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(header)
    w.writerows(new_rows)


def pure_hang_shell(name):
    """Build pure 3.0 mm slope shell without any side walls, front walls, or corner posts."""
    T = np.arange(NX * NY).reshape(NY, NX)
    C = NX * NY + np.arange(NX * NY).reshape(NY, NX)
    verts = np.vstack([
        np.c_[GX.ravel(), GY.ravel(), H.ravel()],
        np.c_[GX.ravel(), GY.ravel(), G.ravel()]
    ])
    jj, ii = np.mgrid[0:NY - 1, 0:NX - 1]
    top_q = np.c_[T[jj, ii].ravel(), T[jj, ii + 1].ravel(), T[jj + 1, ii + 1].ravel(), T[jj + 1, ii].ravel()]
    bot_q = np.c_[C[jj, ii].ravel(), C[jj + 1, ii].ravel(), C[jj + 1, ii + 1].ravel(), C[jj, ii + 1].ravel()]
    rim = []
    for i in range(NX - 1):
        rim.append([T[0, i], C[0, i], C[0, i + 1], T[0, i + 1]])
    for i in range(NX - 1):
        rim.append([T[NY - 1, i + 1], C[NY - 1, i + 1], C[NY - 1, i], T[NY - 1, i]])
    for j in range(NY - 1):
        rim.append([T[j + 1, 0], C[j + 1, 0], C[j, 0], T[j, 0]])
    for j in range(NY - 1):
        rim.append([T[j, NX - 1], C[j, NX - 1], C[j + 1, NX - 1], T[j + 1, NX - 1]])

    grid_q = np.vstack([top_q, bot_q, np.array(rim, dtype=np.int64)])
    flat = grid_q.ravel()
    lens = np.full(len(grid_q), 4, dtype=np.int64)
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", verts.ravel())
    me.loops.add(len(flat))
    me.loops.foreach_set("vertex_index", flat)
    me.polygons.add(len(lens))
    me.polygons.foreach_set("loop_start", np.arange(len(lens), dtype=np.int64) * 4)
    me.polygons.foreach_set("loop_total", lens)
    me.update(calc_edges=True)
    assert me.validate(verbose=False) is False
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    tri_top = np.vstack([top_q[:, [0, 1, 2]], top_q[:, [0, 2, 3]]])
    top_tree = BVHTree.FromPolygons(verts[: NX * NY].tolist(), tri_top.tolist())
    wall_min = min(top_tree.find_nearest(Vector(p))[3] for p in verts[NX * NY::20])
    return obj, {"wall_min": wall_min, "ceiling": (float(G.min()), float(G.max()))}


def tidy(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bad = sum(1 for e in bm.edges if not e.is_manifold)
    loose = sum(1 for v in bm.verts if not v.link_faces)
    vol = bm.calc_volume(signed=True)
    if vol < 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
        vol = -vol
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return bad, loose, vol


def boxes(name, corner_sets):
    bm = bmesh.new()
    for pts in corner_sets:
        vs = [bm.verts.new(Vector(p)) for p in pts]
        for f in ((0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)):
            bm.faces.new([vs[k] for k in f])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    return o


def subtract(obj, cutter):
    mod = obj.modifiers.new("cut", "BOOLEAN")
    mod.operation, mod.solver, mod.object = "DIFFERENCE", "MANIFOLD", cutter
    for o in bpy.context.scene.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter, do_unlink=True)


def subtract_prisms(obj, prisms, name):
    passes = []
    for p in prisms:
        c = p.mean(0)
        for grp in passes:
            if all(np.linalg.norm(c - q.mean(0)) > 3 * HOLE for q in grp):
                grp.append(p)
                break
        else:
            passes.append([p])
    for k, grp in enumerate(passes):
        subtract(obj, boxes(f"{name}_{k}", grp))
    return len(passes)


def frame(n):
    ref = np.array([0.000123, -0.000179, 1.0])
    ref /= np.linalg.norm(ref)
    u = np.cross(n, ref)
    u = u / np.linalg.norm(u) if np.linalg.norm(u) > 1e-6 else np.array([1.0, 0.0, 0.0])
    return u, np.cross(n, u)


def prism(P, n, u, v, half=HOLE / 2, h_in=HOLE_IN):
    ring = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
    return np.array([P + a * half * u + b * half * v + t * n for t in (HOLE_OUT, -h_in) for a, b in ring])


with open(NEW_CSV, newline="") as f:
    LEDS = list(csv.DictReader(f))

holes = []
for led in LEDS:
    lid = int(led["led_id"])
    P = np.array([float(led[k]) for k in ("x_mm", "y_mm", "z_mm")])
    n = np.array([float(led[k]) for k in ("nx", "ny", "nz")])
    n /= np.linalg.norm(n)
    u, v = frame(n)
    # Ensure hole stays inside [2 mm .. WIDTH-2 mm] and [2 mm .. DEPTH-2 mm]
    if P[1] < 8.0:
        y_new = 8.0
        P = np.array([P[0], y_new, surf(P[0], y_new)])
        n = grid_normal(P[0], y_new)
        u, v = frame(n)
    holes.append((lid, P, n, u, v))

with open(HOLE_CSV, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["led_id", "x_mm", "y_mm", "z_mm", "nx", "ny", "nz"])
    for lid, P, n, _u, _v in holes:
        w.writerow([lid, *(round(float(val), 6) for val in P), *(round(float(val), 6) for val in n)])


def min_web(hs):
    t = np.linspace(-1, 1, 61)
    e = np.vstack([np.c_[t, -np.ones_like(t)], np.c_[t, np.ones_like(t)],
                   np.c_[-np.ones_like(t), t], np.c_[np.ones_like(t), t]]) * HOLE / 2
    sq = [P + e[:, :1] * u + e[:, 1:] * v for _, P, n, u, v in hs]
    best, pair = np.inf, None
    for i in range(len(hs)):
        for j in range(i + 1, len(hs)):
            if np.linalg.norm(hs[i][1] - hs[j][1]) < 3 * HOLE:
                d = np.linalg.norm(sq[i][:, None] - sq[j][None], axis=2).min()
                if d < best:
                    best, pair = d, (hs[i][0], hs[j][0])
    return best, pair


def hole_checks(obj, hs, depth_check=5.5):
    bm_tmp = bmesh.new()
    bm_tmp.from_mesh(obj.data)
    tree = BVHTree.FromBMesh(bm_tmp)
    free, closed, fails = 0, 0, []
    for lid, P, n, u, v in hs:
        d = Vector(-n)
        hits = [(round(a, 2), round(b, 2), round(tree.ray_cast(Vector(P + a * u + b * v + RAY0 * n), d, RAY0 + depth_check)[3] - RAY0, 2))
                for a in np.linspace(-2.9, 2.9, 7) for b in np.linspace(-2.9, 2.9, 7)
                if tree.ray_cast(Vector(P + a * u + b * v + RAY0 * n), d, RAY0 + depth_check)[0] is not None]
        edge = all(tree.ray_cast(Vector(P + s * 3.1 * w + RAY0 * n), d, RAY0 + depth_check)[0] is not None
                   for w in (u, v) for s in (-1, 1))
        free += not hits
        closed += edge
        if hits or not edge:
            fails.append((lid, len(hits), hits[:4], edge))
    bm_tmp.free()
    if fails:
        print("HOLE_FAILS:", fails)
    return tree, free, closed


for old_name in ("Hang_Endmodell_Druck", "Hang_Endmodell_Ausstellung"):
    old_o = bpy.data.objects.get(old_name)
    if old_o:
        bpy.data.objects.remove(old_o, do_unlink=True)

full, info = pure_hang_shell("Hang_Endmodell_Druck")
pre = tidy(full)
assert pre[0] == 0 and pre[1] == 0, ("shell before holes", pre)

# Pre-triangulate the shell BEFORE Boolean hole subtraction
bm_pre = bmesh.new()
bm_pre.from_mesh(full.data)
bmesh.ops.triangulate(bm_pre, faces=list(bm_pre.faces), quad_method="FIXED", ngon_method="EAR_CLIP")
bm_pre.to_mesh(full.data)
bm_pre.free()
full.data.update()

HOLE_DEPTH_IN = 7.5
npass = subtract_prisms(full, [prism(P, n, u, v, h_in=HOLE_DEPTH_IN) for _, P, n, u, v in holes], "Loecher")
bad, loose, vol = tidy(full)
assert bad == 0 and loose == 0, (bad, loose)

bm = bmesh.new()
bm.from_mesh(full.data)
bmesh.ops.triangulate(bm, faces=list(bm.faces), quad_method="BEAUTY", ngon_method="EAR_CLIP")
bm.to_mesh(full.data)
bm.free()
full.data.update()

_, free_55, closed_55 = hole_checks(full, holes, depth_check=5.5)
_, free_65, closed_65 = hole_checks(full, holes, depth_check=6.5)
assert free_55 == 109 and closed_55 == 109, (free_55, closed_55)
assert free_65 == 109 and closed_65 == 109, (free_65, closed_65)
web, web_pair = min_web(holes)
assert web >= 1.0, (web, web_pair)

# Save a duplicate in exhibition orientation ("Hang_Endmodell_Ausstellung") before rotating to print orientation
me_aus = full.data.copy()
me_aus.name = "Hang_Endmodell_Ausstellung"
obj_aus = bpy.data.objects.new("Hang_Endmodell_Ausstellung", me_aus)
bpy.context.scene.collection.objects.link(obj_aus)

# Export exhibition orientation STL as reference
for o in bpy.context.scene.objects:
    o.select_set(False)
obj_aus.select_set(True)
bpy.context.view_layer.objects.active = obj_aus
bpy.ops.wm.stl_export(filepath=str(NEW_STL_AUSSTELLUNG), export_selected_objects=True, ascii_format=False)

# Rotate Hang_Endmodell_Druck by exact right-handed 90 deg rotation around Y-axis:
# X_print = Z_max - Z_model
# Y_print = Y_model
# Z_print = X_model (so the planar S-curved edge X_model = 0 sits 100% flush on Z_print = 0.000 mm!)
co_arr = np.empty(len(full.data.vertices) * 3)
full.data.vertices.foreach_get("co", co_arr)
co_arr = co_arr.reshape(-1, 3)
z_max_model = float(co_arr[:, 2].max())
x_print = z_max_model - co_arr[:, 2]
y_print = co_arr[:, 1].copy()
z_print = co_arr[:, 0].copy()
co_print = np.column_stack([x_print, y_print, z_print])
full.data.vertices.foreach_set("co", co_print.ravel())
full.data.update()

bad_p, loose_p, vol_p = tidy(full)
assert bad_p == 0 and loose_p == 0, (bad_p, loose_p)

if "PLA_weiss" in bpy.data.materials and not full.data.materials:
    full.data.materials.append(bpy.data.materials["PLA_weiss"])
if "PLA_weiss" in bpy.data.materials and not obj_aus.data.materials:
    obj_aus.data.materials.append(bpy.data.materials["PLA_weiss"])

# Export support-free print STL
for o in bpy.context.scene.objects:
    o.select_set(False)
full.hide_set(False)
full.select_set(True)
bpy.context.view_layer.objects.active = full
bpy.ops.wm.stl_export(filepath=str(NEW_STL), export_selected_objects=True, ascii_format=False)

# Verify exported binary STL
with open(NEW_STL, "rb") as f:
    f.seek(80)
    ntri = int.from_bytes(f.read(4), "little")
    raw_stl = np.frombuffer(f.read(), dtype=np.uint8).reshape(ntri, 50)
    tris = np.frombuffer(raw_stl[:, 12:48].tobytes(), dtype=np.float32).reshape(ntri, 3, 3)

_, idx = np.unique(tris.reshape(-1, 3), axis=0, return_inverse=True)
f_idx = idx.reshape(-1, 3)
e0 = np.sort(f_idx[:, [0, 1]], axis=1)
e1 = np.sort(f_idx[:, [1, 2]], axis=1)
e2 = np.sort(f_idx[:, [2, 0]], axis=1)
edges_all = np.vstack([e0, e1, e2])
_, counts = np.unique(edges_all, axis=0, return_counts=True)
stl_non_manifold = int(np.sum(counts != 2))
assert stl_non_manifold == 0, f"STL has {stl_non_manifold} non-manifold edges"

bbox_min = tris.reshape(-1, 3).min(axis=0).round(3).tolist()
bbox_max = tris.reshape(-1, 3).max(axis=0).round(3).tolist()
bbox_size = (tris.reshape(-1, 3).max(axis=0) - tris.reshape(-1, 3).min(axis=0)).round(3).tolist()
assert bbox_size[0] <= 325.0 and bbox_size[1] <= 320.0 and bbox_size[2] <= 320.0, f"Exceeds H2D single-nozzle volume: {bbox_size}"

# Organize scene collections cleanly
def ensure_collection(name):
    c = bpy.data.collections.get(name)
    if not c:
        c = bpy.data.collections.new(name)
    if c.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(c)
    return c


def move_to_collection(obj, target):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    target.objects.link(obj)


c_druck = ensure_collection("01_Druckmodell")
c_ref = ensure_collection("02_Referenz")
c_kanaele = ensure_collection("03_LED_Kanaele")

move_to_collection(full, c_druck)
move_to_collection(obj_aus, c_ref)
obj_aus.hide_set(True)
obj_aus.hide_render = True
body.hide_set(True)
body.hide_render = True
move_to_collection(body, c_ref)

for o in list(bpy.data.objects):
    if o.name.startswith("LED_"):
        move_to_collection(o, c_ref)
        o.hide_set(True)
        o.hide_render = True
    elif o.name.startswith("Helfer_") or o.name.startswith("Schnitt_") or o.name.startswith("Test"):
        bpy.data.objects.remove(o, do_unlink=True)

old_box = bpy.data.objects.get("Bambu_H2D_Bauraum_350x320x325")
if old_box:
    bpy.data.objects.remove(old_box, do_unlink=True)
bm_box = bmesh.new()
bmesh.ops.create_cube(bm_box, size=1.0)
for v in bm_box.verts:
    v.co = Vector(((v.co.x + 0.5) * 325.0, (v.co.y + 0.5) * 320.0, (v.co.z + 0.5) * 320.0))
for f in list(bm_box.faces):
    bm_box.faces.remove(f)
me_box = bpy.data.meshes.new("Bambu_H2D_Bauraum_325x320x320")
bm_box.to_mesh(me_box)
bm_box.free()
box_obj = bpy.data.objects.new("Bambu_H2D_Bauraum_325x320x320", me_box)
box_obj.display_type = "WIRE"
box_obj.hide_render = True
move_to_collection(box_obj, c_ref)

c_kanaele.hide_viewport = True
c_kanaele.hide_render = True

bpy.ops.wm.save_as_mainfile(filepath=str(NEW_BLEND))

metrics = {
    "mode": "pure_hang_support_free_standing_on_edge",
    "exhibition_dimensions_mm": [WIDTH, DEPTH, round(float(H.max()), 3)],
    "print_bbox_min_mm": bbox_min,
    "print_bbox_max_mm": bbox_max,
    "print_bbox_size_mm": bbox_size,
    "bambu_h2d_single_nozzle_volume_mm": [325.0, 320.0, 320.0],
    "fits_single_print": True,
    "support_required": False,
    "max_overhang_from_vertical_deg": round(max_overhang_x_deg, 2),
    "triangles": ntri,
    "non_manifold_edges": stl_non_manifold,
    "loose_verts": loose_p,
    "volume_cm3": round(vol_p / 1000.0, 2),
    "mass_solid_pla_g": round(vol_p / 1000.0 * PLA, 1),
    "wall_thickness_target_mm": WALL,
    "wall_thickness_min_mm": round(info["wall_min"], 3),
    "led_count": len(holes),
    "hole_size_mm": HOLE,
    "holes_free_5_5mm": free_55,
    "holes_free_6_5mm": free_65,
    "holes_closed_5_5mm": closed_55,
    "min_web_mm": round(float(web), 3),
    "min_web_pair": web_pair,
    "side_walls": "removed (pure 3.0 mm slope shell)",
    "print_orientation": "standing on planar S-curved edge X_model=0 at Z_print=0.0 mm",
    "stl_sha256": hashlib.sha256(NEW_STL.read_bytes()).hexdigest(),
}
(OUT / "metriken_v4.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False))
print("SUCCESS_METRICS:", json.dumps(metrics, indent=2, ensure_ascii=False))

