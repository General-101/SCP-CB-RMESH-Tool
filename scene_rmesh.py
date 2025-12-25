import re
import os
import bpy
import bmesh
import colorsys

from mathutils import Euler, Matrix, Vector, Quaternion
from .process_rmesh import TextureType, write_rmesh, read_rmesh
from . import ObjectType
from math import radians, pi, degrees, asin, atan2
from .B3DParser import B3DTree
from .scene_b3d import import_node_recursive
from bpy_extras.image_utils import load_image

DTOR = pi / 180.0
RTOD = 180.0 / pi

def is_string_empty(string):
    is_empty = False
    if not string == None and (len(string) == 0 or string.isspace()):
        is_empty = True

    return is_empty

def lim32(n):
    """Simulate a 32 bit unsigned interger overflow"""
    return n & 0xFFFFFFFF

# Ported from https://github.com/preshing/RandomSequence
class PreshingSequenceGenerator32:
    """Peusdo-random sequence generator that repeats every 2**32 elements"""
    @staticmethod
    def __permuteQPR(x):
        prime = 4294967291
        if x >= prime: # The 5 integers out of range are mapped to themselves.
            return x

        residue = lim32(x**2 % prime)
        if x <= (prime // 2):
            return residue

        else:
            return lim32(prime - residue)

    def __init__(self, seed_base = None, seed_offset = None):
        import time
        if seed_base == None:
            seed_base = lim32(int(time.time() * 100000000)) ^ 0xac1fd838

        if seed_offset == None:
            seed_offset = lim32(int(time.time() * 100000000)) ^ 0x0b8dedd3

        self.__index = PreshingSequenceGenerator32.__permuteQPR(lim32(PreshingSequenceGenerator32.__permuteQPR(seed_base) + 0x682f0161))
        self.__intermediate_offset = PreshingSequenceGenerator32.__permuteQPR(lim32(PreshingSequenceGenerator32.__permuteQPR(seed_offset) + 0x46790905))

    def next(self):
        self.__index = lim32(self.__index + 1)
        index_permut = PreshingSequenceGenerator32.__permuteQPR(self.__index)
        return PreshingSequenceGenerator32.__permuteQPR(lim32(index_permut + self.__intermediate_offset) ^ 0x5bf03635)

class RandomColorGenerator(PreshingSequenceGenerator32):
    def next(self):
        rng = super().next()
        h = (rng >> 16) / 0xFFF # [0, 1]
        saturation_raw = (rng & 0xFF) / 0xFF
        brightness_raw = (rng >> 8 & 0xFF) / 0xFF
        v = brightness_raw * 0.3 + 0.5 # [0.5, 0.8]
        s = saturation_raw * 0.4 + 0.6 # [0.3, 1]
        rgb = colorsys.hsv_to_rgb(h, s, v)
        colors = (rgb[0], rgb[1] , rgb[2], 1)
        return colors

def natural_key(s):
    return [int(t) if t.isdigit() else t.lower()
            for t in re.split(r'(\d+)', s)]

def get_referenced_collection(collection_name, parent_collection, hide_render=False, hide_viewport=False):
    asset_collection = bpy.data.collections.get(collection_name)
    if asset_collection == None:
        asset_collection = bpy.data.collections.new(collection_name)
        parent_collection.children.link(asset_collection)
        if not parent_collection.name == "Scene Collection":
            asset_collection.tag_collection.parent = parent_collection

    asset_collection.hide_render = hide_render
    asset_collection.hide_viewport = hide_viewport

    return asset_collection

def get_linked_node(node, input_name, search_type):
    linked_node = None
    node_input = node.inputs[input_name]
    if node_input.is_linked:
        for node_link in node_input.links:
            if node_link.from_node.type == search_type:
                linked_node = node_link.from_node
                break

    return linked_node

def connect_inputs(tree, output_node, output_name, input_node, input_name):
    tree.links.new(output_node.outputs[output_name], input_node.inputs[input_name])

def get_output_material_node(mat):
    output_material_node = None
    if not mat == None and mat.use_nodes and not mat.node_tree == None:
        for node in mat.node_tree.nodes:
            if node.type == "OUTPUT_MATERIAL" and node.is_active_output:
                output_material_node = node
                break

    if output_material_node is None:
        output_material_node = mat.node_tree.nodes.new("ShaderNodeOutputMaterial")

    return output_material_node

def get_file(file_name, is_image=True):
    file_name = os.path.basename(file_name).lower()
    result = file_name.rsplit(".", 1)
    if len(result) == 1 and not is_image:
        file_name = "%s.b3d" % file_name

    file_asset = None
    file_path = ""
    game_path = bpy.context.preferences.addons["io_scene_rmesh"].preferences.game_path

    if not is_string_empty(game_path):
        for root, dirs, files in os.walk(game_path):
            for file in files:
                if file.lower() == file_name:
                    file_path = os.path.join(root, file)
                    break

    if is_image:
        if os.path.isfile(file_path):
            file_asset = bpy.data.images.load(file_path, check_existing=True)
    else:
        file_asset = file_path
        
    return file_asset

def get_material_name(ob, tri):
    mat_name = "UNASSIGNED"
    mat_count = len(ob.material_slots)
    ob_mat_idx = tri.material_index
    if 0 <= ob_mat_idx < mat_count:
        mat_slot = ob.material_slots[ob_mat_idx]
        if mat_slot.link == 'OBJECT':
            if mat_slot is not None:
                mat_name = mat_slot.material.name
        else:
            if ob.data.materials[ob_mat_idx] is not None:
                mat_name = ob.data.materials[ob_mat_idx].name

    return mat_name

def pitch_quat(p):
    return Quaternion((1.0, 0.0, 0.0), p)

def yaw_quat(y):
    return Quaternion((0.0, 1.0, 0.0), y)

def roll_quat(r):
    return Quaternion((0.0, 0.0, 1.0), r)

def rotation_quat(p, y, r):
    return yaw_quat(y) @ pitch_quat(p) @ roll_quat(r)

def get_blender_rot(euler_rotation):
    p, y, r = euler_rotation
    y = -y
    quat = rotation_quat(p * DTOR, y * DTOR, r * DTOR)
    return quat.normalized()

def get_blitz_rot(rot):
    q = rot.normalized()
    m = q.to_matrix()

    if abs(m[1][2]) < 0.999999:
        pitch = asin(-m[1][2])
        yaw   = atan2(m[0][2], m[2][2])
        roll  = atan2(m[1][0], m[1][1])
    else:
        pitch = asin(-m[1][2])
        yaw   = atan2(-m[2][0], m[0][0])
        roll  = 0.0

    yaw = -yaw

    return (pitch * RTOD, yaw * RTOD, roll * RTOD)

def export_scene(context, filepath, report):
    rmesh_dict = {
        "rmesh_file_type": "RoomMesh",
        "meshes": [],
        "collision_meshes": [],
        "entities": []
    }

    game_path = bpy.context.preferences.addons["io_scene_rmesh"].preferences.game_path

    mesh_collection = get_referenced_collection("meshes", context.scene.collection, False)
    collision_collection = get_referenced_collection("collisions", context.scene.collection, True)
    entity_collection = get_referenced_collection("entities", context.scene.collection, False)

    pivot_matrix = Matrix.Rotation(radians(-90), 4, 'X') @  Matrix.Diagonal((-1.0, 1.0, 1.0, 1.0)) @ Matrix.Scale(160.0, 4)
    depsgraph = context.evaluated_depsgraph_get()

    section_data = {}
    for ob in mesh_collection.objects:
        if ob.type != 'MESH':
            continue

        ob_eval = ob.evaluated_get(depsgraph)
        mesh = ob_eval.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
        mesh.calc_loop_triangles()

        layer_uv_0 = mesh.uv_layers.get("uvmap_render")
        layer_uv_1 = mesh.uv_layers.get("uvmap_lightmap")
        layer_color = mesh.color_attributes.get("color")

        for tri in mesh.loop_triangles:
            mat_name = get_material_name(ob, tri)
            if mat_name not in section_data:
                section_data[mat_name] = {"textures": [], "vertices": [], "triangles": [], "vertex_map": {}}
                lightmap_texture_dict = {"texture_type": 0, "texture_name": ""}
                diffuse_texture_dict = {"texture_type": 0, "texture_name": ""}

                mat = bpy.data.materials.get(mat_name)
                if mat.use_nodes:
                    for node in mat.node_tree.nodes:
                        if node.type == 'TEX_IMAGE':
                            image = node.image
                            if not image:
                                continue

                            if image.filepath:
                                filename = os.path.basename(bpy.path.abspath(image.filepath))
                                name_no_ext = os.path.splitext(filename)[0]
                                if "_lm" in name_no_ext.lower():
                                    lightmap_texture_dict["texture_type"] = TextureType.lightmap.value
                                    lightmap_texture_dict["texture_name"] = filename
                                    break

                    output_material_node = get_output_material_node(mat)
                    bdsf_principled = get_linked_node(output_material_node, "Surface", "BSDF_PRINCIPLED")
                    image_node_a = get_linked_node(bdsf_principled, "Base Color", "TEX_IMAGE")
                    image_node_b = get_linked_node(bdsf_principled, "Alpha", "TEX_IMAGE")

                    if image_node_a is not None:
                        diffuse_texture_dict["texture_type"] = TextureType.opaque.value
                        if image_node_a.image.filepath:
                            diffuse_texture_dict["texture_name"] = os.path.basename(bpy.path.abspath(image_node_a.image.filepath))

                        if image_node_a == image_node_b:
                            diffuse_texture_dict["texture_type"] = TextureType.transparent.value
 
                section_data[mat_name]["textures"].append(lightmap_texture_dict)
                section_data[mat_name]["textures"].append(diffuse_texture_dict)

            mesh_section = section_data[mat_name]
            vertex_map = mesh_section["vertex_map"]
            tri_indices = []
            for loop_index in tri.loops:
                loop = mesh.loops[loop_index]
                v = mesh.vertices[loop.vertex_index]

                pos = pivot_matrix @ (ob_eval.matrix_world @ v.co)

                uv1 = (0.0, 0.0)
                uv2 = (0.0, 0.0)
                if layer_uv_0:
                    u0, v0 = layer_uv_0.data[loop_index].uv
                    uv1 = (u0, 1 - v0)

                if layer_uv_1:
                    u1, v1 = layer_uv_1.data[loop_index].uv
                    uv2 = (u1, 1 - v1)

                color = (0, 0, 0)
                if layer_color:
                    r, g, b, a = layer_color.data[loop_index].color
                    color = (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))

                key = (round(pos.x, 6), round(pos.y, 6), round(pos.z, 6), uv1, uv2, color)
                if key not in vertex_map:
                    vertex_map[key] = len(mesh_section["vertices"])
                    mesh_section["vertices"].append({"position": pos, "uv1": uv1, "uv2": uv2, "color": color})

                tri_indices.append(vertex_map[key])

            mesh_section["triangles"].append({"a": tri_indices[2], "b": tri_indices[1], "c": tri_indices[0]})

        ob_eval.to_mesh_clear()

    for mesh_dict in section_data.values():
        rmesh_dict["meshes"].append(mesh_dict)

    for ob in collision_collection.objects:
        if ob.type == 'MESH':
            ob_eval = ob.evaluated_get(depsgraph)
            mesh = ob_eval.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
            mesh.calc_loop_triangles()

            mesh_dict = {
                "vertices": [],
                "triangles": []
            }
            for v in mesh.vertices:
                pos = pivot_matrix @ (ob_eval.matrix_world @ v.co)
                mesh_dict["vertices"].append({"position": pos})

            for tri in mesh.loop_triangles:
                tri_indices = [mesh.loops[loop_index].vertex_index for loop_index in tri.loops]
                mesh_dict["triangles"].append({"a": tri_indices[2], "b": tri_indices[1], "c": tri_indices[0]})

            ob_eval.to_mesh_clear()
            rmesh_dict["collision_meshes"].append(mesh_dict)

    object_names = []
    ALLOWED_TYPES = ('MESH', 'EMPTY', 'LIGHT', 'SPEAKER')
    for ob in entity_collection.objects:
        if ob.type in ALLOWED_TYPES:
            object_names.append(ob.name)

    object_names.sort(key=natural_key)
    for object_name in object_names:
        ob = bpy.data.objects.get(object_name)
        if ob is not None:
            object_type = ObjectType(int(ob.rmesh.object_type))
            loc, rot, scale = (pivot_matrix @ ob.matrix_world).decompose()
            if object_type == ObjectType.entity_screen:
                entity_dict = {}

                entity_dict["entity_type"] = "screen"
                entity_dict["position"] = loc
                entity_dict["texture_name"] = bpy.path.abspath(ob.rmesh.texture_path).split(game_path, 1)[0]
                rmesh_dict["entities"].append(entity_dict)

            elif object_type == ObjectType.entity_save_screen:
                entity_dict = {}

                entity_dict["entity_type"] = "save_screen"
                entity_dict["position"] = loc
                entity_dict["model_name"] = os.path.basename(bpy.path.abspath(ob.rmesh.model_path))
                entity_dict["euler_rotation"] = get_blitz_rot(rot)
                entity_dict["scale"] = scale
                entity_dict["texture_name"] = bpy.path.abspath(ob.rmesh.texture_path).split(game_path, 1)[0]
                rmesh_dict["entities"].append(entity_dict)

            elif object_type == ObjectType.entity_waypoint:
                entity_dict = {}

                entity_dict["entity_type"] = "waypoint"
                entity_dict["position"] = loc
                rmesh_dict["entities"].append(entity_dict)

            elif object_type == ObjectType.entity_light:
                r, g, b = ob.data.color
                entity_dict = {}

                entity_dict["entity_type"] = "light"
                entity_dict["position"] = loc
                entity_dict["range"] = ob.data.cutoff_distance
                entity_dict["color"] = "%s %s %s" % (round(r * 255), round(g * 255), round(b * 255))
                entity_dict["intensity"] = ob.data.energy  / 50
                rmesh_dict["entities"].append(entity_dict)

            elif object_type == ObjectType.entity_light_fix:
                r, g, b = ob.data.color
                entity_dict = {}

                entity_dict["entity_type"] = "light_fix"
                entity_dict["position"] = loc
                entity_dict["color"] = "%s %s %s" % (round(r * 255), round(g * 255), round(b * 255))
                entity_dict["intensity"] = ob.data.energy  / 50
                entity_dict["range"] = ob.data.cutoff_distance
                rmesh_dict["entities"].append(entity_dict)

            elif object_type == ObjectType.entity_spotlight:
                r, g, b = ob.data.color
                entity_dict = {}

                entity_dict["entity_type"] = "spotlight"
                entity_dict["position"] = loc
                entity_dict["range"] = ob.data.cutoff_distance
                entity_dict["color"] = "%s %s %s" % (round(r * 255), round(g * 255), round(b * 255))
                entity_dict["intensity"] = ob.data.energy  / 50
                p, y, r = get_blitz_rot(rot)
                entity_dict["euler_rotation"] = "%s %s %s" % (p, y, r)
                entity_dict["inner_cone_angle"] = 0
                entity_dict["outer_cone_angle"] = 0
                rmesh_dict["entities"].append(entity_dict)

            elif object_type == ObjectType.entity_sound_emitter:
                entity_dict = {}

                entity_dict["entity_type"] = "soundemitter"
                entity_dict["position"] = loc
                entity_dict["id"] = ob.rmesh.sound_emitter_id
                entity_dict["range"] = ob.data.distance_max
                rmesh_dict["entities"].append(entity_dict)

            elif object_type == ObjectType.entity_model:
                entity_dict = {}

                entity_dict["entity_type"] = "model"
                entity_dict["model_name"] = os.path.basename(bpy.path.abspath(ob.rmesh.model_path))
                rmesh_dict["entities"].append(entity_dict)

            elif object_type == ObjectType.entity_mesh:
                entity_dict = {}

                entity_dict["entity_type"] = "mesh"
                entity_dict["position"] = loc
                entity_dict["model_name"] = os.path.basename(bpy.path.abspath(ob.rmesh.model_path))
                entity_dict["euler_rotation"] = get_blitz_rot(rot)
                entity_dict["scale"] = scale
                entity_dict["has_collision"] = int(ob.rmesh.has_collision)
                entity_dict["fx"] = ob.rmesh.fx
                entity_dict["texture_name"] = bpy.path.abspath(ob.rmesh.texture_path).split(game_path, 1)[0]
                rmesh_dict["entities"].append(entity_dict)

    write_rmesh(rmesh_dict, filepath)

    report({'INFO'}, "Export completed successfully")
    return {'FINISHED'}

def import_scene(context, filepath, report):
    rmesh_dict = read_rmesh(filepath)

    game_path = bpy.context.preferences.addons["io_scene_rmesh"].preferences.game_path

    pivot_matrix = Matrix.Rotation(radians(90), 4, 'X') @  Matrix.Diagonal((-1.0, 1.0, 1.0, 1.0)) @ Matrix.Scale(0.00625, 4)

    mesh_collection = get_referenced_collection("meshes", context.scene.collection, False)
    collision_collection = get_referenced_collection("collisions", context.scene.collection, True)
    entity_collection = get_referenced_collection("entities", context.scene.collection, False)

    random_color_gen = RandomColorGenerator() # generates a random sequence of colors

    full_mesh = bpy.data.meshes.new("room_mesh")
    object_mesh = bpy.data.objects.new("room_mesh", full_mesh)
    object_mesh.rmesh.object_type = str(ObjectType.mesh.value)
    mesh_collection.objects.link(object_mesh)

    error_log = set()

    bm = bmesh.new()
    for mesh_idx, mesh_dict in enumerate(rmesh_dict["meshes"]):
        mesh = bpy.data.meshes.new("temp_mesh_%s" % mesh_idx)

        vertices = [pivot_matrix @ Vector(vertex["position"]) for vertex in mesh_dict["vertices"]]
        triangles = [[triangle["c"], triangle["b"], triangle["a"]] for triangle in mesh_dict["triangles"]]
        mesh.from_pydata(vertices, [], triangles)

        mat = bpy.data.materials.new(name="texture_%s" % mesh_idx)
        mat.diffuse_color = random_color_gen.next()
        mesh.materials.append(mat)
        full_mesh.materials.append(mat)

        mat.use_nodes = True
        for node in mat.node_tree.nodes:
            mat.node_tree.nodes.remove(node)

        output_material_node = get_output_material_node(mat)
        output_material_node.location = Vector((0.0, 0.0))

        bdsf_principled = get_linked_node(output_material_node, "Surface", "BSDF_PRINCIPLED")
        if bdsf_principled is None:
            bdsf_principled = mat.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
            connect_inputs(mat.node_tree, bdsf_principled, "BSDF", output_material_node, "Surface")

        bdsf_principled.location = (-440.0, 0.0)

        lightmap_type = TextureType.none
        texture_lightmap = None
        diffuse_type = TextureType.none
        texture_diffuse = None
        for texture_idx, texture_dict in enumerate(mesh_dict["textures"]):
            if texture_idx == 0:
                lightmap_type = TextureType(texture_dict["texture_type"])
                texture_lightmap_data = get_file(texture_dict["texture_name"])
                if texture_lightmap_data:
                    texture_lightmap = mat.node_tree.nodes.new("ShaderNodeTexImage")
                    texture_lightmap.image = texture_lightmap_data
                    texture_lightmap.image.alpha_mode = 'CHANNEL_PACKED'
                    texture_lightmap.location = (-720.0, -320.0)
                elif len(texture_dict["texture_name"]) > 0:
                    error_log.add('Failed to retrive "%s"' % texture_dict["texture_name"])

            elif texture_idx == 1:
                diffuse_type = TextureType(texture_dict["texture_type"])
                texture_diffuse_data = get_file(texture_dict["texture_name"])
                if texture_diffuse_data:
                    texture_diffuse = mat.node_tree.nodes.new("ShaderNodeTexImage")
                    texture_diffuse.image = texture_diffuse_data
                    texture_diffuse.image.alpha_mode = 'CHANNEL_PACKED'
                    texture_diffuse.location = (-720.0, 0.0)
                    connect_inputs(mat.node_tree, texture_diffuse, "Color", bdsf_principled, "Base Color")
                    if diffuse_type == TextureType.transparent:
                        connect_inputs(mat.node_tree, texture_diffuse, "Alpha", bdsf_principled, "Alpha")
                elif len(texture_dict["texture_name"]) > 0:
                    error_log.add('Failed to retrive "%s"' % texture_dict["texture_name"])
                    report({'WARNING'}, 'Failed to retrive "%s"' % texture_dict["texture_name"])

        layer_color = mesh.color_attributes.new("color", "BYTE_COLOR", "CORNER")
        layer_uv_0 = mesh.uv_layers.new(name="uvmap_render")
        layer_uv_1 = mesh.uv_layers.new(name="uvmap_lightmap")
        for poly in mesh.polygons:
            poly.use_smooth = True
            poly.material_index = mesh_idx
            for loop_index in poly.loop_indices:
                vert_index = mesh.loops[loop_index].vertex_index
                vertex = mesh_dict["vertices"][vert_index]
                layer_uv_0.data[loop_index].uv = (vertex["uv1"][0], 1 - vertex["uv1"][1])
                layer_uv_1.data[loop_index].uv = (vertex["uv2"][0], 1 - vertex["uv2"][1])
                layer_color.data[loop_index].color = (vertex["color"][0] / 255, vertex["color"][1] / 255, vertex["color"][2] / 255, 1.0)

        bm.from_mesh(mesh)
        bpy.data.meshes.remove(mesh)

    bm.to_mesh(full_mesh)
    bm.free()

    for coll_mesh_idx, coll_mesh_dict in enumerate(rmesh_dict["collision_meshes"]):
        coll_mesh = bpy.data.meshes.new("coll_mesh_%s" % coll_mesh_idx)
        coll_object_mesh = bpy.data.objects.new("coll_object_%s" % coll_mesh_idx, coll_mesh)
        coll_object_mesh.rmesh.object_type = str(ObjectType.collision.value)
        collision_collection.objects.link(coll_object_mesh)

        coll_vertices = [pivot_matrix @ Vector(coll_vertex["position"]) for coll_vertex in coll_mesh_dict["vertices"]]
        coll_triangles = [[coll_triangle["c"], coll_triangle["b"], coll_triangle["a"]] for coll_triangle in coll_mesh_dict["triangles"]]
        coll_mesh.from_pydata(coll_vertices, [], coll_triangles)
        for poly in coll_mesh.polygons:
            poly.use_smooth = True

    entity_meshes = {}
    images = {}
    material_mapping = {}
    IMAGE_SEARCH=True
    for entity_idx, entity_dict in enumerate(rmesh_dict["entities"]):
        if entity_dict["entity_type"] == "screen":
            object_mesh = bpy.data.objects.new("%s screen" % entity_idx, None)
            object_mesh.rmesh.object_type = str(ObjectType.entity_screen.value)
            object_mesh.empty_display_type = 'IMAGE'

            file_path = get_file(entity_dict["texture_name"], False)
            object_mesh.rmesh.texture_path = file_path
            if os.path.isfile(file_path):
                file_asset = bpy.data.images.load(file_path, check_existing=True)
                object_mesh.data = file_asset

            entity_collection.objects.link(object_mesh)
            object_mesh.location = pivot_matrix @ Vector(entity_dict["position"])

        elif entity_dict["entity_type"] == "save_screen":
            object_mesh = bpy.data.objects.new("%s save_screen" % entity_idx, None)
            object_mesh.rmesh.object_type = str(ObjectType.entity_save_screen.value)
            entity_collection.objects.link(object_mesh)

            rotation = get_blender_rot(entity_dict["euler_rotation"])
            global_transform = Matrix.LocRotScale(Vector(entity_dict["position"]), rotation, Vector(entity_dict["scale"]))
            object_mesh.matrix_world = pivot_matrix @ global_transform

            model_path = get_file(entity_dict["model_name"], False)
            texture_path = get_file(entity_dict["texture_name"], False)
            object_mesh.rmesh.model_path = model_path
            object_mesh.rmesh.texture_path = texture_path

        elif entity_dict["entity_type"] == "waypoint":
            object_mesh = bpy.data.objects.new("%s waypoint" % entity_idx, None)
            object_mesh.rmesh.object_type = str(ObjectType.entity_waypoint.value)
            entity_collection.objects.link(object_mesh)
            object_mesh.location = pivot_matrix @ Vector(entity_dict["position"])

        elif entity_dict["entity_type"] == "light":
            object_data = bpy.data.lights.new("%s light" % entity_idx, "POINT")
            object_mesh = bpy.data.objects.new("%s light" % entity_idx, object_data)
            object_mesh.rmesh.object_type = str(ObjectType.entity_light.value)
            entity_collection.objects.link(object_mesh)

            object_mesh.location = pivot_matrix @ Vector(entity_dict["position"])
            object_data.energy = entity_dict["intensity"] * 50
            object_data.shadow_soft_size = entity_dict["range"] / 1000
            object_data.use_custom_distance = True
            object_data.cutoff_distance = entity_dict["range"]
            r, g, b = entity_dict["color"].split(" ")
            object_data.color = (int(r) / 255, int(g) / 255, int(b) / 255)

        elif entity_dict["entity_type"] == "light_fix":
            object_data = bpy.data.lights.new("%s light_fix" % entity_idx, "POINT")
            object_mesh = bpy.data.objects.new("%s light_fix" % entity_idx, object_data)
            object_mesh.rmesh.object_type = str(ObjectType.entity_light_fix.value)
            entity_collection.objects.link(object_mesh)

            object_mesh.location = pivot_matrix @ Vector(entity_dict["position"])
            object_data.energy = entity_dict["intensity"] * 50
            object_data.shadow_soft_size = entity_dict["range"] / 1000
            object_data.use_custom_distance = True
            object_data.cutoff_distance = entity_dict["range"]
            r, g, b = entity_dict["color"].split(" ")
            object_data.color = (int(r) / 255, int(g) / 255, int(b) / 255)

        elif entity_dict["entity_type"] == "spotlight":
            object_data = bpy.data.lights.new("%s spotlight" % entity_idx, "SPOT")
            object_mesh = bpy.data.objects.new("%s spotlight" % entity_idx, object_data)
            object_mesh.rmesh.object_type = str(ObjectType.entity_spotlight.value)
            entity_collection.objects.link(object_mesh)

            p, y, r = entity_dict["euler_rotation"].split(" ")
            rotation = get_blender_rot([float(p), float(y), float(r)])
            global_transform = Matrix.LocRotScale(Vector(entity_dict["position"]), rotation, Vector((1, 1, 1)))
            object_mesh.matrix_world = pivot_matrix @ global_transform

            object_data.energy = entity_dict["intensity"] * 50
            object_data.shadow_soft_size = entity_dict["range"] / 1000
            object_data.use_custom_distance = True
            object_data.cutoff_distance = entity_dict["range"]
            r, g, b = entity_dict["color"].split(" ")
            object_data.color = (int(r) / 255, int(g) / 255, int(b) / 255)

            outer_deg: float = max(1.0, min(180.0, entity_dict["outer_cone_angle"]))
            inner_deg: float = max(1.0, min(180.0, entity_dict["inner_cone_angle"]))
            ratio = inner_deg / outer_deg if outer_deg > 0.0 else 1.0

            object_data.spot_size = radians(outer_deg)
            object_data.spot_blend = max(0.0, min(1.0, 1.0 - ratio))

        elif entity_dict["entity_type"] == "soundemitter":
            speaker_data = bpy.data.speakers.new("%s soundemitter" % entity_idx)
            object_mesh = bpy.data.objects.new("%s soundemitter" % entity_idx, speaker_data)
            object_mesh.rmesh.object_type = str(ObjectType.entity_sound_emitter.value)
            entity_collection.objects.link(object_mesh)
            object_mesh.location = pivot_matrix @ Vector(entity_dict["position"])
            object_mesh.rmesh.sound_emitter_id = entity_dict["id"]
            object_mesh.data.distance_max = entity_dict["range"]

        elif entity_dict["entity_type"] == "model":
            object_mesh = bpy.data.objects.new("%s model" % entity_idx, None)
            object_mesh.rmesh.object_type = str(ObjectType.entity_model.value)
            entity_collection.objects.link(object_mesh)
            model_path = get_file(entity_dict["model_name"], False)
            object_mesh.rmesh.model_path = model_path

        elif entity_dict["entity_type"] == "mesh":
            model_path = get_file(entity_dict["model_name"], False)
            texture_path = get_file(entity_dict["texture_name"], False)
            ob_data = entity_meshes.get(model_path)
            
            if ob_data is None and model_path:
                ob_data = entity_meshes[model_path] = bpy.data.meshes.new("%s mesh" % entity_idx)
                data = B3DTree().parse(model_path)
                for i, texture in enumerate(data['textures'] if 'textures' in data else []):
                    texture_name = os.path.basename(texture['name'])
                    for mat in data.materials:
                        if mat.tids[0]==i:
                            images[i] = (texture_name, load_image(texture_name, game_path, check_existing=True,
                                place_holder=False, recursive=IMAGE_SEARCH))

                for i, mat in enumerate(data.materials if 'materials' in data else []):
                    material = bpy.data.materials.new(mat.name)
                    material.diffuse_color = random_color_gen.next()
                    material_mapping[i] = material.name
                    #material.diffuse_color = mat.rgba
                    material.blend_method = 'BLEND' if mat.rgba[3] < 1.0 else 'OPAQUE'

                    tid = mat.tids[0] if len(mat.tids) else -1

                    if tid in images:
                        name, image = images[tid]
                        texture = bpy.data.textures.new(name=name, type='IMAGE')
                        material.use_nodes = True
                        bsdf = material.node_tree.nodes["Principled BSDF"]
                        texImage = material.node_tree.nodes.new('ShaderNodeTexImage')
                        texImage.image = image
                        material.node_tree.links.new(bsdf.inputs['Base Color'], texImage.outputs['Color'])

                for key, value in material_mapping.items():
                    ob_data.materials.append(bpy.data.materials[value])

                bm = bmesh.new()
                import_node_recursive(data, material_mapping, bm)
                bm.to_mesh(ob_data)
                bm.free()

            object_mesh = bpy.data.objects.new("%s mesh" % entity_idx, ob_data)
            object_mesh.rmesh.object_type = str(ObjectType.entity_mesh.value)
            entity_collection.objects.link(object_mesh)

            object_mesh.rmesh.model_path = model_path
            object_mesh.rmesh.texture_path = texture_path

            rotation = get_blender_rot(entity_dict["euler_rotation"])
            global_transform = Matrix.LocRotScale(Vector(entity_dict["position"]), rotation, Vector(entity_dict["scale"]))
            object_mesh.matrix_world = pivot_matrix @ global_transform

            object_mesh.rmesh.has_collision = bool(entity_dict["has_collision"])
            object_mesh.rmesh.fx = entity_dict["fx"]

    for error in error_log:
        report({'WARNING'}, error)

    report({'INFO'}, "Export completed successfully")
    return {'FINISHED'}

