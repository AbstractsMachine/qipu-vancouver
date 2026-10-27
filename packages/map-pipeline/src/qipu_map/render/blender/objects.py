"""The terrain, buildings and trees of one frame (runs inside Blender)."""

import math

import bpy
import numpy as np
from materials import flat_value, srgb_to_linear
from mathutils import Vector

ROOF_CLASS = 7


def link(scene, name, data):
    obj = bpy.data.objects.new(name, data)
    scene.collection.objects.link(obj)
    return obj


def build_terrain(scene, ground):
    """The terrain as a grid of quads through the DEM cell centres, its UVs on the class grid."""
    dem = ground["dem"].astype(np.float64)
    x0, y0, cell = (float(v) for v in ground["dem_origin"])
    if dem.shape == (1, 1):
        dem = np.full((2, 2), dem[0, 0])
        cell /= 2
    stride = max(1, math.ceil(math.sqrt(dem.size / 1_000_000)))
    dem = dem[::stride, ::stride]
    cell *= stride
    h, w = dem.shape
    jj, ii = np.meshgrid(np.arange(w), np.arange(h))
    xs = x0 + (jj + 0.5) * cell
    ys = y0 - (ii + 0.5) * cell
    verts = np.stack([xs, ys, dem], axis=-1).reshape(-1, 3)
    a = (ii[:-1, :-1] * w + jj[:-1, :-1]).ravel()
    # counter-clockwise from above: south-west, south-east, north-east, north-west
    quads = np.stack([a + w, a + w + 1, a + 1, a], axis=-1)
    mesh = bpy.data.meshes.new("terrain")
    mesh.vertices.add(len(verts))
    mesh.vertices.foreach_set("co", verts.astype(np.float32).ravel())
    mesh.loops.add(quads.size)
    mesh.loops.foreach_set("vertex_index", quads.astype(np.int32).ravel())
    mesh.polygons.add(len(quads))
    mesh.polygons.foreach_set("loop_start", (np.arange(len(quads)) * 4).astype(np.int32))
    mesh.polygons.foreach_set("loop_total", np.full(len(quads), 4, dtype=np.int32))
    gx0, gy0, gcell = (float(v) for v in ground["classes_origin"])
    gh, gw = ground["classes"].shape
    loop_xy = verts[quads.ravel(), :2]
    uv = np.stack([(loop_xy[:, 0] - gx0) / (gw * gcell), (loop_xy[:, 1] - (gy0 - gh * gcell)) / (gh * gcell)], axis=-1)
    layer = mesh.uv_layers.new(name="ground")
    layer.data.foreach_set("uv", uv.astype(np.float32).ravel())
    mesh.update(calc_edges=True)
    mesh.validate()
    return link(scene, "terrain", mesh)


def corner_colour(mesh, name, per_face):
    """A colour per face, stored on the face corners (the domain the flat passes read), in exact floats."""
    attr = mesh.color_attributes.new(name, "FLOAT_COLOR", "CORNER")
    totals = [len(p.vertices) for p in mesh.polygons]
    rgba = np.repeat(np.asarray(per_face, dtype=np.float32), totals, axis=0)
    attr.data.foreach_set("color", rgba.ravel())


def build_buildings(scene, job, frame, wall, roof):
    class_colours = {int(k): v for k, v in job["class_colours"].items()}
    objects = []
    for i in frame["buildings"]:
        b = job["buildings"][i]
        verts = np.asarray(b["vertices"], dtype=np.float64)
        origin = np.array([verts[:, 0].mean(), verts[:, 1].mean(), b["ground"]])
        mesh = bpy.data.meshes.new(f"b{b['index']}")
        mesh.from_pydata((verts - origin).tolist(), [], b["faces"])
        mesh.materials.append(wall)
        mesh.materials.append(roof)
        mesh.polygons.foreach_set("material_index", [1 if c == ROOF_CLASS else 0 for c in b["classes"]])
        v = b["index"] + 1
        bid = ((v >> 16) & 255, (v >> 8) & 255, v & 255)
        corner_colour(mesh, "qclass", [[*flat_value(class_colours[c]), 1.0] for c in b["classes"]])
        corner_colour(mesh, "qid", [[*flat_value(bid), 1.0]] * len(b["classes"]))
        mesh.update()
        obj = link(scene, mesh.name, mesh)
        obj.location = Vector(origin.tolist())
        obj["wall"] = srgb_to_linear(b["wall"])
        obj["roof"] = srgb_to_linear(b["roof"])
        obj["glass"] = srgb_to_linear(b["glass"])
        obj["tower"] = 1.0 if b["tower"] else 0.0
        objects.append(obj)
    return objects


def tree_prototypes():
    """One crown per form, unit sized: a sphere for broadleaf trees, a cone for conifers. Trees are linked copies."""
    import bmesh  # noqa: PLC0415 (only inside Blender)

    protos = {}
    for name, make in (
        ("broadleaf", lambda bm: bmesh.ops.create_icosphere(bm, subdivisions=2, radius=0.5)),
        (
            "conifer",
            lambda bm: bmesh.ops.create_cone(bm, segments=10, radius1=0.5, radius2=0.0, depth=1.0, cap_ends=True),
        ),
    ):
        bm = bmesh.new()
        make(bm)
        mesh = bpy.data.meshes.new(f"tree_{name}")
        bm.to_mesh(mesh)
        bm.free()
        for p in mesh.polygons:
            p.use_smooth = True
        protos[name] = mesh
    return protos


def build_trees(scene, job, frame, material):
    x0, y0, x1, y1 = frame["region"]
    protos = tree_prototypes()
    for mesh in protos.values():
        mesh.materials.append(material)
    objects = []
    for k, t in enumerate(job["trees"]):
        if not (x0 <= t["x"] <= x1 and y0 <= t["y"] <= y1):
            continue
        crown = t["crown"]
        if t["conifer"]:
            obj = link(scene, f"tree{k}", protos["conifer"])
            tall = max(t["height"] * 0.8, crown)
            obj.scale = (crown, crown, tall)
            obj.location = (t["x"], t["y"], t["z"] + t["height"] - tall / 2)
        else:
            obj = link(scene, f"tree{k}", protos["broadleaf"])
            obj.scale = (crown, crown, crown)
            obj.location = (t["x"], t["y"], t["z"] + max(t["height"] - crown / 2, crown / 2))
        objects.append(obj)
    return protos, objects
