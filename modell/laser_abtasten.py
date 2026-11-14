"""Stage 1 of the laser export: sample the top surface of the walled v4 model.

Run headless:
  /Applications/Blender.app/Contents/MacOS/Blender -b modell/hang_sagami_endmodell_v4_mit_waenden.blend \
      --python modell/laser_abtasten.py

Writes modell/export/laser_v1/oberflaeche_05mm.npz with the unscaled height grid
(z in mm on a 0.5 mm grid over x and y). The LED holes let rays fall through; those
samples are detected and filled from their neighbours.
"""
import os

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

OBJ = "Hang_Endmodell_Druck"
STEP = 0.5
OUT_DIR = os.path.join(os.path.dirname(bpy.data.filepath), "export", "laser_v1")


def sample():
    dg = bpy.context.evaluated_depsgraph_get()
    obj = bpy.data.objects[OBJ]
    bvh = BVHTree.FromObject(obj, dg)
    mw = obj.matrix_world
    inv = mw.inverted()
    corners = [mw @ Vector(c) for c in obj.bound_box]
    x0, x1 = min(v.x for v in corners), max(v.x for v in corners)
    y0, y1 = min(v.y for v in corners), max(v.y for v in corners)
    ztop = max(v.z for v in corners) + 10.0
    down = (inv.to_3x3() @ Vector((0, 0, -1))).normalized()
    xs = np.arange(x0, x1 + 1e-6, STEP)
    ys = np.arange(y0, y1 + 1e-6, STEP)
    z = np.full((len(xs), len(ys)), np.nan)
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            # nudge edge samples inward so rays at the exact border still hit
            xx = min(max(x, x0 + 0.01), x1 - 0.01)
            yy = min(max(y, y0 + 0.01), y1 - 0.01)
            hit = bvh.ray_cast(inv @ Vector((xx, yy, ztop)), down)
            if hit[0] is not None:
                z[i, j] = (mw @ hit[0]).z
    return xs - x0, ys - y0, z, (x0, y0)


def fill_holes(z):
    from numpy.lib.stride_tricks import sliding_window_view as sw

    bad = np.isnan(z)
    zz = np.where(bad, -1e9, z)
    pad = np.pad(zz, 4, mode="edge")
    med = np.median(sw(pad, (9, 9)), axis=(2, 3))
    bad |= (med - zz) > 3.0
    # grow by one sample: hole walls give intermediate heights at the rim
    g = np.pad(bad, 1)
    bad = g[1:-1, 1:-1] | g[:-2, 1:-1] | g[2:, 1:-1] | g[1:-1, :-2] | g[1:-1, 2:]
    z = np.where(bad, np.nan, z)
    n_bad = int(bad.sum())
    for _ in range(200):
        if not np.isnan(z).any():
            break
        p = np.pad(z, 1, constant_values=np.nan)
        nb = np.stack([p[:-2, 1:-1], p[2:, 1:-1], p[1:-1, :-2], p[1:-1, 2:]])
        cnt = (~np.isnan(nb)).sum(0)
        mean = np.where(cnt > 0, np.nansum(nb, 0) / np.maximum(cnt, 1), np.nan)
        z = np.where(np.isnan(z), mean, z)
    assert not np.isnan(z).any(), "hole filling did not converge"
    return z, n_bad


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    xs, ys, z, origin = sample()
    z, n_bad = fill_holes(z)
    out = os.path.join(OUT_DIR, "oberflaeche_05mm.npz")
    np.savez_compressed(out, xs=xs, ys=ys, z=z, origin=np.array(origin), step=STEP)
    print(f"SAMPLED grid {z.shape}, filled {n_bad} hole samples, "
          f"x 0..{xs[-1]:.1f} y 0..{ys[-1]:.1f} z {z.min():.1f}..{z.max():.1f} -> {out}")


main()
