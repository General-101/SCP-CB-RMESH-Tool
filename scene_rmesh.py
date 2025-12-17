# ##### BEGIN MIT LICENSE BLOCK #####
#
# MIT License
#
# Copyright (c) 2023 Steven Garcia
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# ##### END MIT LICENSE BLOCK #####

import os
import bpy
import math
import bmesh
import colorsys

from mathutils import Matrix, Vector
from .process_rmesh import TextureType, write_rmesh, read_rmesh

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

def get_image_node(mat, texture_name):
    map_node = None

    texture_path = ""
    game_path = bpy.context.preferences.addons["io_scene_rmesh"].preferences.game_path
    if not is_string_empty(game_path):
        for root, dirs, files in os.walk(game_path):
            for file in files:
                if file == texture_name:
                    texture_path = os.path.join(root, file)
                    break

    if os.path.isfile(texture_path):
        texture_image = bpy.data.images.load(texture_path, check_existing=True)
        if texture_image:
            map_node = mat.node_tree.nodes.new("ShaderNodeTexImage")
            map_node.image = texture_image
            map_node.image.alpha_mode = 'CHANNEL_PACKED'

    return map_node

def export_scene(context, filepath, report):
    rmesh_dict = {
        "rmesh_file_type": "RoomMesh",
        "meshes": [],
        "collision_meshes": [],
        "entities": []
    }

    rot_x = Matrix.Rotation(math.radians(-90), 4, 'X')
    scale_x = Matrix.Scale(-1, 4, (1, 0, 0))

    transform = scale_x @ rot_x

    depsgraph = context.evaluated_depsgraph_get()

    for ob in bpy.data.objects:
        if ob.type == 'MESH':
            ob_eval = ob.evaluated_get(depsgraph)
            mesh = ob_eval.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
            mesh.calc_loop_triangles()

            mesh_dict = {
                "textures": [],
                "vertices": [],
                "triangles": []
            }
            vertex_map = {}

            layer_uv_0 = mesh.uv_layers.get("uvmap_render")
            layer_uv_1 = mesh.uv_layers.get("uvmap_lightmap")
            layer_color = mesh.color_attributes.get("color")
            for texture_idx in range(2):
                texture_dict = {}

                texture_dict["texture_type"] = 0
                texture_dict["texture_name"] = ""
                if TextureType(texture_dict["texture_type"]) is not TextureType.none:
                    texture_dict["texture_name"] = ""

                #if texture_idx == 1:
                    #texture_dict["texture_type"] = TextureType.opaque.value
                    #texture_dict["texture_name"] = "white.jpg"

                #if texture_idx == 0:
                    #texture_dict["texture_type"] = TextureType.lightmap.value
                    #texture_dict["texture_name"] = "cont1_038_lm.png"

                mesh_dict["textures"].append(texture_dict)

            for tri in mesh.loop_triangles:
                tri_indices = []

                for loop_index in tri.loops:
                    loop = mesh.loops[loop_index]
                    v = mesh.vertices[loop.vertex_index]

                    pos = transform @ (ob_eval.matrix_world @ v.co)

                    uv1 = (0.0, 0.0)
                    uv2 = (0.0, 0.0)
                    if layer_uv_0 is not None:
                        u0, v0 = layer_uv_0.data[loop_index].uv
                        uv1 = (u0, 1 - v0)
                    if layer_uv_1 is not None:
                        u1, v1 = layer_uv_1.data[loop_index].uv
                        uv2 = (u1, 1 - v1)

                    color = (0, 0, 0)
                    if layer_color is not None:
                        print(layer_color)
                        r, g, b, a = tuple(layer_color.data[loop_index])
                        color = (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))

                    key = (
                        round(pos.x, 6), round(pos.y, 6), round(pos.z, 6),
                        uv1, uv2, color
                    )

                    if key not in vertex_map:
                        vertex_map[key] = len(mesh_dict["vertices"])
                        mesh_dict["vertices"].append({
                            "position": pos,
                            "uv1": uv1,
                            "uv2": uv2,
                            "color": color,
                        })

                    tri_indices.append(vertex_map[key])

                mesh_dict["triangles"].append({
                    "a": tri_indices[2],
                    "b": tri_indices[1],
                    "c": tri_indices[0],
                })

            ob_eval.to_mesh_clear()
            rmesh_dict["meshes"].append(mesh_dict)

        if False:
            write_unsigned_int(rmesh_stream, len(rmesh_dict["collision_meshes"]))
            for collision_dict in rmesh_dict["collision_meshes"]:
                write_unsigned_int(rmesh_stream, len(collision_dict["vertices"]))
                for vertex_dict in collision_dict["vertices"]:
                    write_vector(rmesh_stream, vertex_dict["position"])

                write_unsigned_int(rmesh_stream, len(mesh_dict["triangles"]))
                for triangle_dict in mesh_dict["triangles"]:
                    write_unsigned_int(rmesh_stream, triangle_dict["a"])
                    write_unsigned_int(rmesh_stream, triangle_dict["b"])
                    write_unsigned_int(rmesh_stream, triangle_dict["c"])

            write_unsigned_int(rmesh_stream, len(rmesh_dict["entities"]))
            if has_room_template: # original this was the arg rt in the original function. Need to find out if this is just a given. - Gen
                for entity_dict in rmesh_dict["entities"]:
                    write_string(rmesh_stream, entity_dict["entity_type"])
                    if entity_dict["entity_type"] == "screen":
                        write_vector(rmesh_stream, entity_dict["position"]) # Not sure if this is actually a position but it's 3 floats. - Gen
                        write_string(rmesh_stream, entity_dict["texture_name"])

                    elif entity_dict["entity_type"] == "save_screen":
                        write_vector(rmesh_stream, entity_dict["position"])
                        write_string(rmesh_stream, entity_dict["texture_name"])
                        write_vector(rmesh_stream, entity_dict["euler_rotation"])
                        write_vector(rmesh_stream, entity_dict["scale"])
                        write_string(rmesh_stream, entity_dict["image_path"])

                    elif entity_dict["entity_type"] == "waypoint":
                        write_vector(rmesh_stream, entity_dict["position"])

                    elif entity_dict["entity_type"] == "light":
                        write_vector(rmesh_stream, entity_dict["position"])
                        write_float(rmesh_stream, entity_dict["radius"])
                        write_string(rmesh_stream, entity_dict["light_color"])
                        write_float(rmesh_stream, entity_dict["intensity"])

                    elif entity_dict["entity_type"] == "light_fix":
                        write_vector(rmesh_stream, entity_dict["position"])
                        write_string(rmesh_stream, entity_dict["light_color"])
                        write_float(rmesh_stream, entity_dict["intensity"])
                        write_float(rmesh_stream, entity_dict["radius"])

                    elif entity_dict["entity_type"] == "spotlight":
                        write_vector(rmesh_stream, entity_dict["position"])
                        write_float(rmesh_stream, entity_dict["radius"])
                        write_string(rmesh_stream, entity_dict["light_color"])
                        write_float(rmesh_stream, entity_dict["intensity"])
                        write_string(rmesh_stream, entity_dict["angles"])
                        write_unsigned_int(rmesh_stream, entity_dict["inner_cone_angle"])
                        write_unsigned_int(rmesh_stream, entity_dict["outer_cone_angle"])

                    elif entity_dict["entity_type"] == "soundemitter":
                        write_vector(rmesh_stream, entity_dict["position"])
                        write_unsigned_int(rmesh_stream, entity_dict["id"])
                        write_float(rmesh_stream, entity_dict["radius"])

                    elif entity_dict["entity_type"] == "model":
                        write_string(rmesh_stream, entity_dict["model_name"])

                    elif entity_dict["entity_type"] == "mesh":
                        write_vector(rmesh_stream, entity_dict["position"])
                        write_string(rmesh_stream, entity_dict["mesh_name"])
                        write_vector(rmesh_stream, entity_dict["euler_rotation"])
                        write_vector(rmesh_stream, entity_dict["scale"])
                        write_byte(rmesh_stream, entity_dict["has_collision"])
                        write_unsigned_int(rmesh_stream, entity_dict["fx"])
                        write_string(rmesh_stream, entity_dict["texture_name"])

    write_rmesh(rmesh_dict, filepath)

    report({'INFO'}, "Export completed successfully")
    return {'FINISHED'}

def import_scene(context, filepath, report):
    rmesh_dict = read_rmesh(filepath)

    rot_x = Matrix.Rotation(math.radians(90), 4, 'X')
    scale_x = Matrix.Scale(-1, 4, (1, 0, 0))

    transform = scale_x @ rot_x

    mesh_collection = get_referenced_collection("meshes", context.scene.collection, False)
    collision_collection = get_referenced_collection("collisions", context.scene.collection, False)
    entity_collection = get_referenced_collection("entities", context.scene.collection, False)

    random_color_gen = RandomColorGenerator() # generates a random sequence of colors

    full_mesh = bpy.data.meshes.new("room_mesh")
    object_mesh = bpy.data.objects.new("room_mesh", full_mesh)
    mesh_collection.objects.link(object_mesh)

    bm = bmesh.new()
    for mesh_idx, mesh_dict in enumerate(rmesh_dict["meshes"]):
        mesh = bpy.data.meshes.new("temp_mesh_%s" % mesh_idx)

        vertices = [transform @ Vector(vertex["position"]) for vertex in mesh_dict["vertices"]]
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

        lightmap_type = TextureType.none
        texture_lightmap = None
        diffuse_type = TextureType.none
        texture_diffuse = None
        for texture_idx, texture_dict in enumerate(mesh_dict["textures"]):
            if texture_idx == 0:
                lightmap_type = TextureType(texture_dict["texture_type"])
                texture_lightmap = get_image_node(mat, texture_dict["texture_name"])

            elif texture_idx == 1:
                diffuse_type = TextureType(texture_dict["texture_type"])
                texture_diffuse = get_image_node(mat, texture_dict["texture_name"])
                if texture_diffuse:
                    connect_inputs(mat.node_tree, texture_diffuse, "Color", bdsf_principled, "Base Color")
                    if diffuse_type == TextureType.transparent:
                        connect_inputs(mat.node_tree, texture_diffuse, "Alpha", bdsf_principled, "Alpha")

        layer_color = mesh.color_attributes.new("color", "BYTE_COLOR", "CORNER")
        layer_uv_0 = mesh.uv_layers.new(name="uvmap_render")
        layer_uv_1 = mesh.uv_layers.new(name="uvmap_lightmap")
        for poly in mesh.polygons:
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
        collision_collection.objects.link(coll_object_mesh)

        coll_vertices = [transform @ Vector(coll_vertex["position"]) for coll_vertex in coll_mesh_dict["vertices"]]
        coll_triangles = [[coll_triangle["a"], coll_triangle["b"], coll_triangle["c"]] for coll_triangle in coll_mesh_dict["triangles"]]
        coll_mesh.from_pydata(coll_vertices, [], coll_triangles)

    for entity_idx, entity_dict in enumerate(rmesh_dict["entities"]):
        if entity_dict["entity_type"] == "screen":
            screen_collection = get_referenced_collection("screens", entity_collection, False)
            object_mesh = bpy.data.objects.new("screen %s" % entity_idx, None)
            screen_collection.objects.link(object_mesh)
            object_mesh.location = transform @ Vector(entity_dict["position"])

        elif entity_dict["entity_type"] == "save_screen":
            save_screen_collection = get_referenced_collection("save_screens", entity_collection, False)
            object_mesh = bpy.data.objects.new("save_screen %s" % entity_idx, None)
            save_screen_collection.objects.link(object_mesh)
            object_mesh.location = transform @ Vector(entity_dict["position"])

        elif entity_dict["entity_type"] == "waypoint":
            waypoint_collection = get_referenced_collection("waypoints", entity_collection, False)
            object_mesh = bpy.data.objects.new("waypoint %s" % entity_idx, None)
            waypoint_collection.objects.link(object_mesh)
            object_mesh.location = transform @ Vector(entity_dict["position"])

        elif entity_dict["entity_type"] == "light":
            light_collection = get_referenced_collection("lights", entity_collection, False)
            object_data = bpy.data.lights.new("light %s" % entity_idx, "POINT")
            object_mesh = bpy.data.objects.new("light %s" % entity_idx, object_data)
            light_collection.objects.link(object_mesh)
            object_mesh.location = transform @ Vector(entity_dict["position"])
            object_data.energy = entity_dict["intensity"] * 8000000
            object_data.shadow_soft_size = entity_dict["radius"]
            r, g, b = entity_dict["light_color"].split(" ")
            object_data.color = (int(r) / 255, int(g) / 255, int(b) / 255)

        elif entity_dict["entity_type"] == "light_fix":
            light_fix_collection = get_referenced_collection("light_fix", entity_collection, False)
            object_data = bpy.data.lights.new("light_fix %s" % entity_idx, "POINT")
            object_mesh = bpy.data.objects.new("light_fix %s" % entity_idx, object_data)
            light_fix_collection.objects.link(object_mesh)
            object_mesh.location = transform @ Vector(entity_dict["position"])
            object_data.energy = entity_dict["intensity"] * 8000000
            object_data.shadow_soft_size = entity_dict["radius"]
            r, g, b = entity_dict["light_color"].split(" ")
            object_data.color = (int(r) / 255, int(g) / 255, int(b) / 255)

        elif entity_dict["entity_type"] == "spotlight":
            spotlight_collection = get_referenced_collection("spotlights", entity_collection, False)
            object_data = bpy.data.lights.new("spotlight %s" % entity_idx, "SPOT")
            object_mesh = bpy.data.objects.new("spotlight %s" % entity_idx, object_data)
            spotlight_collection.objects.link(object_mesh)
            object_mesh.location = transform @ Vector(entity_dict["position"])
            object_data.energy = entity_dict["intensity"] * 8000000
            object_data.shadow_soft_size = entity_dict["radius"]
            r, g, b = entity_dict["light_color"].split(" ")
            object_data.color = (int(r) / 255, int(g) / 255, int(b) / 255)

        elif entity_dict["entity_type"] == "soundemitter":
            soundemitter_collection = get_referenced_collection("soundemitters", entity_collection, False)
            object_mesh = bpy.data.objects.new("soundemitter %s" % entity_idx, None)
            soundemitter_collection.objects.link(object_mesh)
            object_mesh.location = transform @ Vector(entity_dict["position"])

        elif entity_dict["entity_type"] == "model":
            model_collection = get_referenced_collection("models", entity_collection, False)
            print("Is this a leftover?")

        elif entity_dict["entity_type"] == "mesh":
            entity_mesh_collection = get_referenced_collection("entity_meshes", entity_collection, False)
            object_mesh = bpy.data.objects.new("mesh %s" % entity_idx, None)
            entity_mesh_collection.objects.link(object_mesh)
            object_mesh.location = transform @ Vector(entity_dict["position"])

    report({'INFO'}, "Export completed successfully")
    return {'FINISHED'}
