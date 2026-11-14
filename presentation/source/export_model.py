"""Export the presentation lattice and 109 signal LEDs from Blender.

Run with:
  Blender -b modell/hang_sagami_laser_v1.blend --python presentation/source/export_model.py
"""
import bpy
import json
import re
from pathlib import Path
from mathutils import Vector

ROOT = Path(bpy.path.abspath("//")).parent
OUT = ROOT / "presentation" / "assets" / "model-data.js"
SCENE = bpy.context.scene
DEPSGRAPH = bpy.context.evaluated_depsgraph_get()


def rgb(obj):
    if obj.data.materials and obj.data.materials[0]:
        return [round(v, 4) for v in obj.data.materials[0].diffuse_color[:3]]
    return [round(v, 4) for v in obj.color[:3]]


def mesh_record(obj, kind):
    evaluated = obj.evaluated_get(DEPSGRAPH)
    mesh = evaluated.to_mesh(preserve_all_data_layers=False, depsgraph=DEPSGRAPH)
    mesh.calc_loop_triangles()
    matrix = evaluated.matrix_world
    # Convert Blender Z-up coordinates to Three.js Y-up coordinates.
    positions = []
    for vertex in mesh.vertices:
        p = matrix @ vertex.co
        positions.extend((round(p.x, 3), round(p.z, 3), round(-p.y, 3)))
    indices = [index for triangle in mesh.loop_triangles for index in triangle.vertices]
    record = {"name": obj.name, "kind": kind, "color": rgb(obj), "positions": positions, "indices": indices}
    evaluated.to_mesh_clear()
    return record


parts = []
for collection_name, kind in (("Laser_Teile", "wood"), ("LED_Reihen_Traeger", "carrier"), ("LED_Streifen_WS2812B", "strip")):
    collection = bpy.data.collections[collection_name]
    for obj in sorted(collection.objects, key=lambda item: item.name):
        if obj.type == "MESH":
            parts.append(mesh_record(obj, kind))

leds = []
pattern = re.compile(r"LED(\d{3})_")
for obj in bpy.data.collections["LED_Signale_109"].objects:
    match = pattern.search(obj.name)
    if not match:
        raise RuntimeError(f"No LED id in {obj.name}")
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    low = Vector((min(point.x for point in corners), min(point.y for point in corners), min(point.z for point in corners)))
    high = Vector((max(point.x for point in corners), max(point.y for point in corners), max(point.z for point in corners)))
    center = (low + high) / 2
    dimensions = high - low
    leds.append({
        "id": int(match.group(1)),
        "name": obj.name,
        "position": [round(center.x, 3), round(center.z, 3), round(-center.y, 3)],
        "size": [round(dimensions.x, 3), round(dimensions.z, 3), round(dimensions.y, 3)],
        "color": rgb(obj),
    })

leds.sort(key=lambda item: item["id"])
if [item["id"] for item in leds] != list(range(1, 110)):
    raise RuntimeError("LED_Signale_109 does not map exactly to LED ids 1..109")

payload = {"source": Path(bpy.data.filepath).name, "parts": parts, "leds": leds}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("window.SAGAMI_GEOMETRY=" + json.dumps(payload, separators=(",", ":")) + ";\n", encoding="utf-8")
print(f"Exported {len(parts)} parts and {len(leds)} LEDs to {OUT}")
