"""Build one frame of the map in Blender and render its three passes.

    blender -b --factory-startup --python build.py -- <job.json> <frame name>

Runs inside Blender (bpy, numpy) with its two neighbours, materials.py and objects.py; it imports nothing from qipu_map,
so the job folder and this folder are all a GPU box needs. Writes `<frame>.beauty.png`, `<frame>.classrgb.png` (the
class pass in flat colours; the driver maps it to ids) and `<frame>.id.png` into the job's output folder.

The beauty pass is the live map's V6 look in Cycles: a sun from the south-west at 50 degrees over a sky fill, a white
city with dark glass by era, deep blue water. The class and id passes are flat emission, one sample, no pixel filter,
stored so the plain sRGB view writes them back exactly: every pixel holds exactly one surface's colour.
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))

from materials import (
    emission_material,
    flat_value,
    ground_images,
    ground_material,
    image_node,
    new_material,
    roof_material,
    tree_material,
    wall_material,
)
from objects import build_buildings, build_terrain, build_trees, link

TREE_CLASS = 6
CAMERA_DISTANCE_M = 20_000.0


def log(*args):
    print("[qipu-render]", *args, flush=True)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    return bpy.context.scene


def camera_axes(azimuth_deg, elevation_deg):
    """The map camera's right, up and forward vectors: the same formulas as qipu_map.geo.camera.ObliqueCamera."""
    a, e = math.radians(azimuth_deg), math.radians(elevation_deg)
    right = Vector((math.cos(a), -math.sin(a), 0.0))
    up = Vector((math.sin(a) * math.sin(e), math.cos(a) * math.sin(e), math.cos(e)))
    forward = Vector((math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), -math.sin(e)))
    return right, up, forward


def build_camera(scene, job, frame):
    """An orthographic camera whose image is exactly the frame's window of the canvas."""
    c = job["canvas"]
    m = c["metres_per_px"]
    right, up, forward = camera_axes(c["azimuth_deg"], c["elevation_deg"])
    sx = c["left"] + (frame["x"] + frame["w"] / 2) * m
    sy = c["top"] - (frame["y"] + frame["h"] / 2) * m
    data = bpy.data.cameras.new("map")
    data.type = "ORTHO"
    data.sensor_fit = "HORIZONTAL"
    data.ortho_scale = frame["w"] * m
    data.clip_start = 1.0
    data.clip_end = 2 * CAMERA_DISTANCE_M
    cam = link(scene, "map", data)
    cam.location = right * sx + up * sy - forward * CAMERA_DISTANCE_M
    cam.rotation_euler = Matrix((right, up, -forward)).transposed().to_euler()
    scene.camera = cam
    scene.render.resolution_x, scene.render.resolution_y = frame["w"], frame["h"]
    scene.render.resolution_percentage = 100
    scene.render.pixel_aspect_x = scene.render.pixel_aspect_y = 1.0
    return cam


def sky_type(sky):
    names = [i.identifier for i in sky.bl_rna.properties["sky_type"].enum_items]
    for wanted in ("MULTIPLE_SCATTERING", "NISHITA", "SINGLE_SCATTERING"):
        if wanted in names:
            return wanted
    return names[0]


def build_light(scene, light):
    """A sun over a physical sky. The sky lights the shade (cool, never violet) and shows in glass and water."""
    world = bpy.data.worlds.new("sky")
    scene.world = world
    world.use_nodes = True
    wn = world.node_tree
    wn.nodes.clear()
    out = wn.nodes.new("ShaderNodeOutputWorld")
    sky = wn.nodes.new("ShaderNodeTexSky")
    sky.sky_type = sky_type(sky)
    sky.sun_disc = False
    a, e = math.radians(light["sun_azimuth_deg"]), math.radians(light["sun_elevation_deg"])
    sky.sun_elevation, sky.sun_rotation = e, a
    fill = wn.nodes.new("ShaderNodeBackground")
    fill.inputs["Strength"].default_value = light["sky_strength"]
    mirror = wn.nodes.new("ShaderNodeBackground")
    mirror.inputs["Strength"].default_value = light["sky_in_reflections"]
    wn.links.new(sky.outputs[0], fill.inputs[0])
    wn.links.new(sky.outputs[0], mirror.inputs[0])
    path = wn.nodes.new("ShaderNodeLightPath")
    mix = wn.nodes.new("ShaderNodeMixShader")
    wn.links.new(path.outputs["Is Glossy Ray"], mix.inputs[0])
    wn.links.new(fill.outputs[0], mix.inputs[1])
    wn.links.new(mirror.outputs[0], mix.inputs[2])
    # The camera never sees the sky: what lies past the terrain is outside the area and stays black.
    void = wn.nodes.new("ShaderNodeBackground")
    void.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
    seen = wn.nodes.new("ShaderNodeMixShader")
    wn.links.new(path.outputs["Is Camera Ray"], seen.inputs[0])
    wn.links.new(mix.outputs[0], seen.inputs[1])
    wn.links.new(void.outputs[0], seen.inputs[2])
    wn.links.new(seen.outputs[0], out.inputs["Surface"])
    data = bpy.data.lights.new("sun", "SUN")
    data.energy = light["sun_energy"]
    data.angle = math.radians(light["sun_angle_deg"])
    data.color = tuple(light["sun_rgb"])
    sun = link(scene, "sun", data)
    to_sun = Vector((math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e)))
    sun.rotation_euler = (-to_sun).to_track_quat("-Z", "Y").to_euler()


def use_device(scene, device):
    """Render on the requested GPU kind. A rented card must use OptiX: under CUDA some materials came out black on the
    live run, so a box without working OptiX refuses rather than render wrong frames."""
    scene.cycles.device = "CPU"
    if device == "CPU":
        return
    prefs = bpy.context.preferences.addons["cycles"].preferences
    try:
        prefs.compute_device_type = device
    except TypeError:
        if device == "OPTIX":
            raise SystemExit(
                "OptiX is not available on this machine; refusing to render under another device"
            ) from None
        log(f"{device} unknown here; rendering on the CPU")
        return
    prefs.get_devices()
    gpus = [d for d in prefs.devices if d.type == device]
    if not gpus:
        if device == "OPTIX":
            raise SystemExit("no OptiX device found; refusing to render under another device")
        log(f"no {device} device; rendering on the CPU")
        return
    for d in prefs.devices:
        d.use = d.type == device
    scene.cycles.device = "GPU"


def beauty_settings(scene, job):
    cy, light = job["cycles"], job["light"]
    scene.render.engine = "CYCLES"
    use_device(scene, os.environ.get("CYCLES_DEVICE", cy["device"]))
    scene.cycles.samples = int(os.environ.get("CYCLES_SAMPLES", cy["samples"]))
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = cy["max_bounces"]
    scene.cycles.filter_width = cy["filter_width"]
    scene.cycles.seed = 0
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = light["agx_look"]
    scene.view_settings.exposure = light["exposure"]
    scene.render.dither_intensity = 0.0


def flat_settings(scene):
    """One sample through each pixel's centre, no denoiser, no tone mapping: emission colours land unchanged."""
    scene.world = None
    scene.cycles.samples = 1
    scene.cycles.use_adaptive_sampling = False
    scene.cycles.use_denoising = False
    scene.cycles.filter_width = 0.01
    scene.cycles.max_bounces = 0
    # Standard is the plain sRGB curve; the flat colours are stored linear (flat_value), so they come out exact.
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    scene.render.dither_intensity = 0.0
    scene.render.film_transparent = False


def write(scene, path):
    s = scene.render.image_settings
    if hasattr(s, "media_type"):
        s.media_type = "IMAGE"
    s.file_format = "PNG"
    s.color_mode = "RGB"
    s.color_depth = "8"
    s.compression = 15
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def assign(meshes, material):
    for mesh in meshes:
        for i in range(len(mesh.materials)):
            mesh.materials[i] = material


def main():
    argv = sys.argv[sys.argv.index("--") + 1 :]
    job_path, name = Path(argv[0]).resolve(), argv[1]
    job = json.loads(job_path.read_text())
    frame = next(f for f in job["frames"] if f["name"] == name)
    out_dir = (job_path.parent / job["out_dir"]).resolve()
    scene = reset()
    ground = dict(np.load(job_path.parent / frame["ground"]))
    colour_img, class_img = ground_images(job, ground)
    terrain = build_terrain(scene, ground)
    terrain.data.materials.append(ground_material(colour_img, class_img))
    buildings = build_buildings(scene, job, frame, wall_material(), roof_material())
    protos, trees = build_trees(scene, job, frame, tree_material())
    build_camera(scene, job, frame)
    build_light(scene, job["light"])
    log(f"{name}: {len(buildings)} buildings, {len(trees)} trees")

    beauty_settings(scene, job)
    write(scene, out_dir / f"{name}.beauty.png")

    flat_settings(scene)
    class_ground, nt, out = new_material("class_ground")
    e = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(image_node(nt, class_img, "Closest").outputs["Color"], e.inputs["Color"])
    nt.links.new(e.outputs[0], out.inputs["Surface"])
    tree_rgb = flat_value(job["class_colours"][str(TREE_CLASS)])
    assign([terrain.data], class_ground)
    assign([o.data for o in buildings], emission_material("class_building", attribute="qclass"))
    assign(protos.values(), emission_material("class_tree", colour=tree_rgb))
    write(scene, out_dir / f"{name}.classrgb.png")

    black = emission_material("black")
    assign([terrain.data], black)
    assign(protos.values(), black)
    assign([o.data for o in buildings], emission_material("id_building", attribute="qid"))
    write(scene, out_dir / f"{name}.id.png")
    log(f"{name}: done")


if __name__ == "__main__":
    main()
