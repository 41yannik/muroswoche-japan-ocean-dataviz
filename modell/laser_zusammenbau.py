"""Stage 3 of the laser export: rebuild the cut parts in 3D as a visual and numeric check.

Run headless (after stage 1 and 2):
  /Applications/Blender.app/Contents/MacOS/Blender -b modell/hang_sagami_endmodell_v4_mit_waenden.blend \
      --python modell/laser_zusammenbau.py -- <render_dir>

Reads modell/export/laser_v1/teile_3d.json and oberflaeche_05mm.npz, extrudes every part to
its thickness, places it in model space (mm, origin at the front-left floor corner), adds a
marker per LED and a 1.075-scaled copy of the model next to the lattice. Saves the result as
modell/hang_sagami_laser_v1.blend (the source blend stays untouched) and renders two
workbench PNGs into <render_dir> (default: modell/export/laser_v1).
"""
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

SRC_OBJ = "Hang_Endmodell_Druck"
HERE = os.path.dirname(bpy.data.filepath)
DATA = os.path.join(HERE, "export", "laser_v1")
OUT_BLEND = os.path.join(HERE, "hang_sagami_laser_v1.blend")
MODEL_OFFSET_X = 340.0  # scaled model copy sits beside the lattice
COLORS = {"side": (0.62, 0.45, 0.28, 1), "strip": (0.85, 0.68, 0.45, 1),
          "cross": (0.55, 0.38, 0.22, 1), "floor": (0.75, 0.6, 0.42, 1)}

# local curve axes (u, v, extrusion) -> world axes, all proper rotations
ROT = {"x": Matrix(((0, 0, 1), (1, 0, 0), (0, 1, 0))),
       "y": Matrix(((1, 0, 0), (0, 0, -1), (0, 1, 0))),
       "z": Matrix.Identity(3)}


def render_dir():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return argv[0] if argv else DATA


def collection(name):
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col


def part_object(p, thick, col):
    cu = bpy.data.curves.new(p["id"], "CURVE")
    cu.dimensions = "2D"
    cu.fill_mode = "BOTH"
    cu.extrude = thick / 2
    for ring in [p["exterior"]] + p["holes"]:
        pts = ring[:-1] if ring[0] == ring[-1] else ring
        sp = cu.splines.new("POLY")
        sp.points.add(len(pts) - 1)
        for pt, (u, v) in zip(sp.points, pts):
            pt.co = (u, v, 0, 1)
        sp.use_cyclic_u = True
    tmp = bpy.data.objects.new(p["id"] + "_kurve", cu)
    col.objects.link(tmp)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg))
    bpy.data.objects.remove(tmp)
    bpy.data.curves.remove(cu)
    ob = bpy.data.objects.new(p["id"], me)
    col.objects.link(ob)
    ax, at = p["place"]["axis"], p["place"]["at"]
    loc = Vector((0, 0, 0))
    loc["xyz".index(ax)] = at + thick / 2
    ob.matrix_world = Matrix.Translation(loc) @ ROT[ax].to_4x4()
    ob.color = COLORS[p["kind"]]
    return ob


def led_markers(leds, col):
    me = bpy.data.meshes.new("led_marker")
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=4.0)
    bm.to_mesh(me)
    bm.free()
    for led in leds:
        ob = bpy.data.objects.new("LED_" + led["led_id"], me)
        ob.location = (led["x_mm"], led["y_mm"], led["z_oberflaeche_mm"] - 4.0)
        ob.color = (0.9, 0.05, 0.05, 1)
        col.objects.link(ob)


def scaled_model(scale, origin, col):
    src = bpy.data.objects[SRC_OBJ]
    ob = src.copy()
    ob.name = "Modell_skaliert_1075"
    col.objects.link(ob)
    x0, y0 = origin
    # same transform as stage 2: world xy shifted to the grid origin, then scaled
    ob.matrix_world = (Matrix.Translation((MODEL_OFFSET_X - x0 * scale, -y0 * scale, 0))
                       @ Matrix.Scale(scale, 4) @ src.matrix_world)
    ob.color = (0.7, 0.72, 0.75, 1)
    ob.hide_render = False  # the copy inherits the hidden flags of the source
    ob.hide_set(False)
    return ob


def top_edge_check(parts, scale, origin):
    """Strip and side plate tops against the scaled model surface, raycast at the plate mid-plane."""
    src = bpy.data.objects[SRC_OBJ]
    dg = bpy.context.evaluated_depsgraph_get()
    bvh = BVHTree.FromObject(src, dg)
    inv = src.matrix_world.inverted()
    down = (inv.to_3x3() @ Vector((0, 0, -1))).normalized()
    x0, y0 = origin
    worst, devs = {}, []
    for p in parts:
        if p["kind"] not in ("strip", "side"):
            continue
        xm = p["place"]["at"] + 1.0
        ext = np.array(p["exterior"])
        d_part = []
        for u in np.arange(math.ceil(ext[:, 0].min()) + 1, ext[:, 0].max() - 1, 2.0):
            # top of the part at this u: highest crossing of the exterior with the vertical line
            a, b = ext[:-1], ext[1:]
            m = (a[:, 0] - u) * (b[:, 0] - u) <= 0
            m &= a[:, 0] != b[:, 0]
            if not m.any():
                continue
            t = (u - a[m, 0]) / (b[m, 0] - a[m, 0])
            vtop = (a[m, 1] + t * (b[m, 1] - a[m, 1])).max()
            hit = bvh.ray_cast(inv @ Vector((x0 + xm / scale, y0 + u / scale, 1000.0)), down)
            if hit[0] is None:
                continue
            zs = (src.matrix_world @ hit[0]).z * scale
            d_part.append(vtop - zs)
        d_part = np.array(d_part)
        worst[p["id"]] = round(float(np.median(np.abs(d_part))), 3)
        devs.append(d_part)
    devs = np.concatenate(devs)
    return {"stichproben": int(devs.size),
            "median_abs_mm": round(float(np.median(np.abs(devs))), 3),
            "p95_abs_mm": round(float(np.percentile(np.abs(devs), 95)), 3),
            "anteil_unter_0_5mm": round(float((np.abs(devs) < 0.5).mean()), 4),
            "median_abs_je_teil": worst}


def render(path, cam_loc, target, ortho_scale=None):
    sc = bpy.context.scene
    cam = bpy.data.objects.get("PruefKamera")
    if cam is None:
        cam = bpy.data.objects.new("PruefKamera", bpy.data.cameras.new("PruefKamera"))
        sc.collection.objects.link(cam)
    cam.data.clip_end = 5000
    cam.data.type = "ORTHO" if ortho_scale else "PERSP"
    if ortho_scale:
        cam.data.ortho_scale = ortho_scale
    else:
        cam.data.lens = 35
    cam.location = cam_loc
    cam.rotation_euler = (Vector(target) - Vector(cam_loc)).to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.light = "STUDIO"
    sc.display.shading.color_type = "OBJECT"
    sc.display.shading.show_cavity = True
    sc.render.resolution_x, sc.render.resolution_y = 1600, 1000
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def main():
    with open(os.path.join(DATA, "teile_3d.json")) as f:
        d = json.load(f)
    with open(os.path.join(DATA, "metriken_laser.json")) as f:
        scale = json.load(f)["skalierung"]
    origin = tuple(np.load(os.path.join(DATA, "oberflaeche_05mm.npz"))["origin"])
    thick = d["dicke"]

    for ob in bpy.context.scene.objects:  # keep the source objects, but out of the renders
        ob.hide_render = True
        ob.hide_set(True)
    col_parts = collection("Laser_Teile")
    objs = [part_object(p, thick, col_parts) for p in d["parts"]]
    led_markers(d["leds"], collection("LED_Marker"))
    scaled_model(scale, origin, collection("Modell_1075"))

    check = top_edge_check(d["parts"], scale, origin)
    dims = {}
    for ob in objs:
        cs = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
        dims[ob.name] = [round(min(c[i] for c in cs), 2) for i in range(3)] + \
                        [round(max(c[i] for c in cs), 2) for i in range(3)]
    allc = np.array(list(dims.values()))
    print("ZUSAMMENBAU bbox lattice min", allc[:, :3].min(0), "max", allc[:, 3:].max(0))
    print("ZUSAMMENBAU oberkante", json.dumps(check))
    with open(os.path.join(DATA, "zusammenbau_pruefung.json"), "w") as f:
        json.dump({"bbox_teile": dims, "oberkante_vs_modell": check}, f, indent=1)

    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND, copy=False)
    rd = render_dir()
    render(os.path.join(rd, "zusammenbau_perspektive.png"), (-150, -620, 620), (320, 140, 90))
    # side view through the open left face: strips and cross bands without S-L and the model copy
    for name in ("S-L", "Modell_skaliert_1075"):
        bpy.data.objects[name].hide_render = True
    render(os.path.join(rd, "zusammenbau_seite.png"), (-600, 140, 135), (0, 140, 135), ortho_scale=470)
    print("ZUSAMMENBAU saved", OUT_BLEND)


main()
