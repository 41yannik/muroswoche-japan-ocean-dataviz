"""Add the 12 horizontal WS2812B LED strip rows, 3D clip-holders, 109 Red-List LEDs, and front paper layer to the Blender scene.

Run headless:
  /Applications/Blender.app/Contents/MacOS/Blender -b modell/hang_sagami_laser_v1.blend \
      --python modell/laser_led_reihen_blender.py
"""
import json
import os
import bpy
import bmesh
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "export", "laser_v1")
STL_DIR = os.path.join(DATA, "stl_led_reihen")
OUT_BLEND = os.path.join(HERE, "hang_sagami_laser_v1.blend")
OUT_BLEND_COPY = os.path.join(HERE, "hang_sagami_led_reihen_v1.blend")

LED_COLORS = {
    "rot": (0.95, 0.08, 0.08, 1.0),
    "orange": (1.0, 0.38, 0.02, 1.0),
    "gelb": (1.0, 0.82, 0.05, 1.0),
    "blau": (0.12, 0.48, 1.0, 1.0),
}


def get_or_new_collection(name):
    if name in bpy.data.collections:
        col = bpy.data.collections[name]
        for ob in list(col.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        return col
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col


def add_box_mesh(name, x0, x1, y0, y1, z0, z1, color, col):
    me = bpy.data.meshes.new(name)
    verts = [
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
    ]
    faces = [
        (0, 3, 2, 1), (4, 5, 6, 7),
        (0, 1, 5, 4), (2, 3, 7, 6),
        (0, 4, 7, 3), (1, 2, 6, 5),
    ]
    me.from_pydata(verts, [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    ob.color = color
    col.objects.link(ob)
    return ob


def interp_curve(pts, y):
    for (u0, z0), (u1, z1) in zip(pts, pts[1:]):
        if u0 <= y <= u1:
            return z0 if u1 == u0 else z0 + (y - u0) / (u1 - u0) * (z1 - z0)
    return pts[-1][1] if y >= pts[-1][0] else pts[0][1]


def build_paper_surface(top_curves, x_rails, col):
    """Build the smooth front paper sheet resting directly on top of S-L, P01..P16, S-R."""
    rail_ids = ["S-L"] + [f"P{k:02d}" for k in range(1, 17)] + ["S-R"]
    ys = [k * 4.0 for k in range(71)]  # 0..280 mm
    verts = []
    faces = []
    nx = len(rail_ids)
    ny = len(ys)
    for ix, (pid, xm) in enumerate(zip(rail_ids, x_rails)):
        pts = top_curves[pid]
        for iy, y in enumerate(ys):
            z = interp_curve(pts, y) + 0.6  # 0.6 mm above rail top
            verts.append((xm, y, z))
    for ix in range(nx - 1):
        for iy in range(ny - 1):
            a = ix * ny + iy
            b = (ix + 1) * ny + iy
            c = (ix + 1) * ny + (iy + 1)
            d = ix * ny + (iy + 1)
            faces.append((a, b, c, d))
    me = bpy.data.meshes.new("Papierschicht_Hang")
    me.from_pydata(verts, [], faces)
    me.update()
    ob = bpy.data.objects.new("Papierschicht_Hang", me)
    ob.color = (0.96, 0.95, 0.91, 0.35)
    ob.show_transparent = True
    col.objects.link(ob)
    return ob


def main():
    with open(os.path.join(DATA, "teile_3d.json")) as f:
        d3 = json.load(f)
    with open(os.path.join(DATA, "led_reihen_3d.json")) as f:
        lr = json.load(f)

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

    x_rails = lr["x_rails"]
    x_gaps = lr["x_gaps"]
    x_leds = lr["x_leds"]
    rail_ids = ["S-L"] + [f"P{k:02d}" for k in range(1, 17)] + ["S-R"]

    col_holders = get_or_new_collection("LED_Reihen_Traeger")
    col_strips = get_or_new_collection("LED_Streifen_WS2812B")
    col_signals = get_or_new_collection("LED_Signale_109")
    col_paper = get_or_new_collection("Papierschicht_Vorne")

    # Hide old single LED_Marker collection in viewport if present so the 12 LED rows stand out clearly
    if "LED_Marker" in bpy.data.collections:
        bpy.data.collections["LED_Marker"].hide_viewport = True
        bpy.data.collections["LED_Marker"].hide_render = True

    active_by_row_gap = {(s["strang"], s["luecke"]): s for s in lr["sharks"]}

    for r in lr["rows"]:
        rid = r["strang"]
        yc = r["y_mm"]
        z_rails = [interp_curve(top_curves[pid], yc) for pid in rail_ids]
        z_bots = [max(0.0, z - 20.0) for z in z_rails]
        z_bot_mean = sum(z_bots) / len(z_bots)

        # 1. Black WS2812B PCB strip (10 mm wide, 300 mm long + overhang for 20 LEDs)
        add_box_mesh(
            f"WS2812B_Streifen_{rid}",
            2.0, 335.0, yc - 5.0, yc + 5.0, z_bot_mean - 2.2, z_bot_mean - 0.5,
            (0.12, 0.12, 0.14, 1.0), col_strips
        )

        # 2. 3D-printed comb-clip carrier bar with 17 light chimneys
        add_box_mesh(
            f"Clip_Traeger_{rid}",
            2.5, 297.5, yc - 5.8, yc + 5.8, z_bot_mean - 4.2, z_bot_mean + 6.0,
            (0.22, 0.62, 0.88, 1.0), col_holders
        )

        # 3. All 20 LEDs on the strip (1..17 in the 17 gaps, 18..20 overhang at right)
        for g in range(1, 21):
            x_led = 150.0 + (g - 9) * (1000.0 / 60.0)
            if g <= 17:
                z_surf = 0.5 * (z_rails[g - 1] + z_rails[g])
                shark = active_by_row_gap.get((rid, g))
                if shark:
                    c = LED_COLORS[shark["farbe"]]
                    # Glowing signal cube at paper level + light chimney column from strip to paper
                    add_box_mesh(
                        f"Signal_{rid}_G{g:02d}_LED{shark['led_id']:03d}_{shark['species'].replace(' ', '_')}",
                        x_gaps[g - 1] - 3.2, x_gaps[g - 1] + 3.2,
                        yc - 3.2, yc + 3.2,
                        z_surf - 20.0, z_surf + 1.2,
                        c, col_signals
                    )
                else:
                    # Inactive LED on the strip (dark grey 5050 package at strip level)
                    add_box_mesh(
                        f"LED_Inaktiv_{rid}_G{g:02d}",
                        x_led - 2.5, x_led + 2.5, yc - 2.5, yc + 2.5,
                        z_bot_mean - 0.5, z_bot_mean + 1.0,
                        (0.28, 0.28, 0.30, 1.0), col_strips
                    )
            else:
                add_box_mesh(
                    f"LED_Ueberhang_{rid}_{g:02d}",
                    x_led - 2.5, x_led + 2.5, yc - 2.5, yc + 2.5,
                    z_bot_mean - 0.5, z_bot_mean + 1.0,
                    (0.28, 0.28, 0.30, 1.0), col_strips
                )

    build_paper_surface(top_curves, x_rails, col_paper)

    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND, copy=False)
    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND_COPY, copy=True)
    print("Saved updated Blender models:", OUT_BLEND, "and", OUT_BLEND_COPY)


if __name__ == "__main__":
    main()
