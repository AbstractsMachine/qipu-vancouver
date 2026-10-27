"""Materials of the map render, built as Cycles node trees (runs inside Blender).

One material serves every building: each object carries its own wall, roof and glass colours as custom properties,
read by Attribute nodes, so a city of 100 000 buildings has a handful of materials. Colours arrive as sRGB from the job
and are turned linear here.
"""

import bpy
import numpy as np


def new_material(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    return mat, mat.node_tree, out


def principled(nt, colour=None, *, roughness=0.8, specular=0.5, metallic=0.0, coat=0.0):
    p = nt.nodes.new("ShaderNodeBsdfPrincipled")
    if colour is not None:
        p.inputs["Base Color"].default_value = (*colour, 1.0)
    p.inputs["Roughness"].default_value = roughness
    p.inputs["Specular IOR Level"].default_value = specular
    p.inputs["Metallic"].default_value = metallic
    p.inputs["Coat Weight"].default_value = coat
    return p


def srgb_to_linear(c):
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def flat_value(rgb8):
    """The linear value that the Standard view writes back as these exact 8-bit sRGB values."""
    return srgb_to_linear([c / 255.0 for c in rgb8])


def math_node(nt, op, a, b=None):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            n.inputs[i].default_value = v
        else:
            nt.links.new(v, n.inputs[i])
    return n.outputs[0]


def object_colour(nt, name):
    """A colour stored on the object as a custom property: one material serves every building."""
    a = nt.nodes.new("ShaderNodeAttribute")
    a.attribute_type = "OBJECT"
    a.attribute_name = name
    return a.outputs["Color"]


def wall_material():
    """Walls with a window grid in the building's own coordinates: glass between bays and floors, none in the first
    4.5 m. Towers get a tighter curtain-wall grid and a more mirror-like glass."""
    mat, nt, out = new_material("wall")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    pos = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], pos.inputs[0])
    nrm = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["True Normal"], nrm.inputs[0])
    along = math_node(
        nt,
        "ADD",
        math_node(nt, "MULTIPLY", pos.outputs[0], math_node(nt, "MULTIPLY", nrm.outputs[1], -1.0)),
        math_node(nt, "MULTIPLY", pos.outputs[1], nrm.outputs[0]),
    )
    tower = nt.nodes.new("ShaderNodeAttribute")
    tower.attribute_type = "OBJECT"
    tower.attribute_name = "tower"
    is_tower = tower.outputs["Fac"]

    def lerp(a, b):
        return math_node(nt, "ADD", a, math_node(nt, "MULTIPLY", is_tower, b - a))

    bay, floor = lerp(2.6, 1.55), lerp(3.4, 3.9)
    u = math_node(nt, "FRACT", math_node(nt, "DIVIDE", along, bay))
    v = math_node(nt, "FRACT", math_node(nt, "DIVIDE", pos.outputs[2], floor))
    half_w, half_h = lerp(0.28, 0.45), lerp(0.29, 0.42)
    in_u = math_node(nt, "LESS_THAN", math_node(nt, "ABSOLUTE", math_node(nt, "SUBTRACT", u, 0.5)), half_w)
    in_v = math_node(nt, "LESS_THAN", math_node(nt, "ABSOLUTE", math_node(nt, "SUBTRACT", v, 0.57)), half_h)
    above = math_node(nt, "GREATER_THAN", pos.outputs[2], 4.5)
    window = math_node(nt, "MULTIPLY", math_node(nt, "MULTIPLY", in_u, in_v), above)
    wall = principled(nt, roughness=0.78, specular=0.4)
    nt.links.new(object_colour(nt, "wall"), wall.inputs["Base Color"])
    glass = principled(nt, roughness=0.05, specular=1.0, coat=0.3)
    nt.links.new(object_colour(nt, "glass"), glass.inputs["Base Color"])
    nt.links.new(math_node(nt, "MULTIPLY", is_tower, 0.5), glass.inputs["Metallic"])
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(window, mix.inputs[0])
    nt.links.new(wall.outputs[0], mix.inputs[1])
    nt.links.new(glass.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    return mat


def roof_material():
    mat, nt, out = new_material("roof")
    p = principled(nt, roughness=0.85, specular=0.3)
    nt.links.new(object_colour(nt, "roof"), p.inputs["Base Color"])
    nt.links.new(p.outputs[0], out.inputs["Surface"])
    return mat


def emission_material(name, attribute=None, colour=(0.0, 0.0, 0.0)):
    """A flat colour for the class and id passes: a mesh attribute or a constant, emitted as is."""
    mat, nt, out = new_material(name)
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Strength"].default_value = 1.0
    if attribute:
        a = nt.nodes.new("ShaderNodeAttribute")
        a.attribute_name = attribute
        nt.links.new(a.outputs["Color"], e.inputs["Color"])
    else:
        e.inputs["Color"].default_value = (*colour, 1.0)
    nt.links.new(e.outputs[0], out.inputs["Surface"])
    return mat


def grid_image(name, rgb, colorspace):
    """An (h, w, 3) float array, north row first, as a float Blender image (whose first row is the south one). A float
    image keeps the values as given; a byte image would pass them through a colour conversion on the way in."""
    h, w, _ = rgb.shape
    img = bpy.data.images.new(name, w, h, alpha=False, float_buffer=True)
    img.colorspace_settings.name = colorspace
    rgba = np.ones((h, w, 4), dtype=np.float32)
    rgba[..., :3] = rgb[::-1]
    img.pixels.foreach_set(rgba.ravel())
    return img


def ground_images(job, ground):
    """The ground's colour (linear) and its class colours (exact, for the flat pass) as two images."""
    classes = ground["classes"]
    ground_lut = np.zeros((256, 3), dtype=np.float32)
    class_lut = np.zeros((256, 3), dtype=np.float32)
    for k, rgb in job["ground_colours"].items():
        ground_lut[int(k)] = srgb_to_linear(rgb)
    for k, rgb in job["class_colours"].items():
        class_lut[int(k)] = flat_value(rgb)
    colour = grid_image("ground_colour", ground_lut[classes], "Linear Rec.709")
    flat = grid_image("ground_class", class_lut[classes], "Non-Color")
    return colour, flat


def image_node(nt, img, interpolation):
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = img
    t.interpolation = interpolation
    t.extension = "CLIP"  # past the grid is outside the area: black, class NONE
    uv = nt.nodes.new("ShaderNodeUVMap")
    uv.uv_map = "ground"
    nt.links.new(uv.outputs[0], t.inputs["Vector"])
    return t


def ground_material(colour_img, class_img):
    """Ground colour from the draped grid; where the grid says water, a deep blue glossy surface mirrors the sky."""
    mat, nt, out = new_material("ground")
    col = image_node(nt, colour_img, "Linear")
    cls = image_node(nt, class_img, "Closest")
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(cls.outputs["Color"], sep.inputs[0])
    is_water = math_node(nt, "GREATER_THAN", sep.outputs[2], 0.9)
    # NONE (black in the class grid) is outside the area: drawn black, as the preview does.
    lum = math_node(nt, "ADD", math_node(nt, "ADD", sep.outputs[0], sep.outputs[1]), sep.outputs[2])
    is_none = math_node(nt, "LESS_THAN", lum, 0.001)
    land = principled(nt, roughness=0.9, specular=0.3)
    nt.links.new(col.outputs["Color"], land.inputs["Base Color"])
    water = principled(nt, srgb_to_linear((0.05, 0.16, 0.28)), roughness=0.04, specular=1.0)
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(is_water, mix.inputs[0])
    nt.links.new(land.outputs[0], mix.inputs[1])
    nt.links.new(water.outputs[0], mix.inputs[2])
    void = nt.nodes.new("ShaderNodeEmission")
    void.inputs["Strength"].default_value = 0.0
    outside = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(is_none, outside.inputs[0])
    nt.links.new(mix.outputs[0], outside.inputs[1])
    nt.links.new(void.outputs[0], outside.inputs[2])
    nt.links.new(outside.outputs[0], out.inputs["Surface"])
    return mat


def tree_material():
    mat, nt, out = new_material("tree")
    p = principled(nt, srgb_to_linear((0.20, 0.33, 0.16)), roughness=0.9, specular=0.2)
    nt.links.new(p.outputs[0], out.inputs["Surface"])
    return mat
