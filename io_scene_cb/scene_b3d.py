import os
import bpy

from . import ObjectType
from pathlib import Path
from bpy_extras import anim_utils
from enum import Enum, auto, Flag
from collections import defaultdict
from math import radians, degrees, floor
from .process_b3d import B3DTree, write_b3d
from mathutils import Matrix, Vector, Quaternion
from .common_functions import (RandomColorGenerator,
                               get_file,
                               is_string_empty,
                               get_material_name,
                               get_linked_node,
                               get_output_material_node,
                               flip,
                               get_shader_node,
                               connect_inputs,
                               generate_texture_mapping,
                               SHADER_RESOURCES,
                               SHADER_NODE_NAMES)

class TextureFXFlags(Flag):
    color = auto()
    alpha = auto()
    masked = auto()
    mipmapped = auto()
    clamp_u = auto()
    clamp_v = auto()
    spherical_environment_map = auto()
    cubic_environment_map = auto()
    store_texture_in_vram = auto()
    force_high_color_textures = auto()
    uses_lightmap_uv = 65536

class TextureBlendEnum(Enum):
    do_not_blend = 0
    no_blend_or_alpha = auto()
    multiply = auto()
    add = auto()
    dot3 = auto()
    multiply2 = auto()

class MaterialFXFlags(Flag):
    full_bright = auto()
    use_vertex_colors_instead_of_brush_color = auto()
    flatshaded = auto()
    disable_fog = auto()
    disable_backface_culling = auto()
    use_vertex_color_alpha_as_transparency = auto()

class MaterialBlendEnum(Enum):
    alpha = 0
    multiply = auto()
    add = auto()

class TextureTypeEnum(Enum):
    lightmap = 0
    diffuse = auto()

def import_mesh(room_scale, node, material_list, is_simple=False, ob_data=None):
    loop_normals = []

    vertices = [room_scale * Vector(flip(vertex)) for vertex in node["vertices"]]
    faces = [face[::-1] for brush in node["faces"] for face in brush["indices"]]
    mesh = bpy.data.meshes.new("mesh")
    mesh.from_pydata(vertices, [], faces)

    # This is for some reason fixing a crash I get when I set custom normals. - Gen
    mesh.validate(clean_customdata=True)

    normal_count = len(node["normals"])
    rgba_count = len(node["rgba"])

    material_indicies = []
    for brush in node["faces"]:
        brush_id = brush["brush_id"]
        if brush_id >= 0:
            for face in brush["indices"]:
                brush_mat = material_list[brush_id]
                if brush_mat.name not in mesh.materials.keys():
                    mesh.materials.append(brush_mat)
                    if is_simple:
                        ob_data.materials.append(brush_mat)

                material_indicies.append(mesh.materials.keys().index(brush_mat.name))

    uv_count = len(node["uvs"][0]) / 2
    layer_uv_0 = mesh.uv_layers.new(name="uvmap_render")
    if uv_count > 1:
        layer_uv_1 = mesh.uv_layers.new(name="uvmap_lightmap")

    material_count = len(material_indicies)
    loop_count = len(mesh.loops)
    layer_color_list = [(1, 1, 1, 1) for i in range(loop_count)]
    layer_alpha_list = [(1, 1, 1, 1) for i in range(loop_count)]
    for poly_idx, poly in enumerate(mesh.polygons):
        poly.use_smooth = True
        if material_count > poly_idx:
            poly.material_index = material_indicies[poly_idx]
        for loop_index in poly.loop_indices:
            vert_index = mesh.loops[loop_index].vertex_index
            if normal_count > 0:
                loop_normals.append(flip(node["normals"][vert_index]))

            if uv_count == 1:
                U0, V0 = node["uvs"][vert_index]
            else:
                U0, V0, U1, V1 = node["uvs"][vert_index]

            layer_uv_0.data[loop_index].uv = (U0, 1 - V0)
            if uv_count > 1:
                layer_uv_1.data[loop_index].uv = (U1, 1 - V1)

            if rgba_count > 0:
                r, g, b, a = node["rgba"][vert_index]
                layer_color_list[loop_index] = (r, g, b, 1)
                layer_alpha_list[loop_index] = (a, a, a, 1)

    if rgba_count > 0:
        layer_color = mesh.color_attributes.new("color", "BYTE_COLOR", "CORNER")
        mesh.attributes.active_color_name = "color"
        mesh.attributes.render_color_index = 0
        for color_idx in range(loop_count):
            r, g, b, a = layer_color_list[color_idx]
            layer_color.data[color_idx].color = (r, g, b, a)

        layer_alpha = mesh.color_attributes.new("alpha", "BYTE_COLOR", "CORNER")
        for color_idx in range(loop_count):
            r, g, b, a = layer_alpha_list[color_idx]
            layer_alpha.data[color_idx].color = (r, g, b, a)

    if normal_count > 0:
        mesh.normals_split_custom_set(loop_normals)

    return mesh

def get_fcurve(fcurves, data_path, index):
    for fc in fcurves:
        if fc.data_path == data_path and fc.array_index == index:
            return fc
    return None

def import_fcurve_data(room_scale, ob, strips, bone_name, keyframe_dict, node_transform, is_bone=True):
    last_position = Vector()
    last_rotation = Quaternion()
    last_scale = Vector((1, 1, 1))
    for strip in strips:
        action = strip.action
        fcurve_map = defaultdict(lambda: defaultdict(dict))
        data_paths={
            "location": 3,
            "rotation_euler": 3,
            "rotation_quaternion": 4,
            "scale": 3
        }

        for path,count in data_paths.items():
            for index in range(count):
                if is_bone:
                    fcurve_data_path = f'pose.bones["{bone_name}"].{path}'
                    group_name = bone_name
                    slot_name = ob.name

                else:
                    fcurve_data_path = path
                    group_name = ob.name
                    slot_name = ob.name

                if (5,0,0)<=bpy.app.version:
                    if action.slots:
                        action_slot = action.slots[0]

                    else:
                        action_slot = action.slots.new(id_type='OBJECT', name=slot_name)
                        strip.action_slot = action_slot

                    channelbag = anim_utils.action_ensure_channelbag_for_slot(action, action_slot)
                    fcurve = channelbag.fcurves.ensure(fcurve_data_path, index=index, group_name=group_name)

                else:
                    fcurve = get_fcurve(action.fcurves, fcurve_data_path, index)
                    if not fcurve:
                        fcurve = action.fcurves.new(data_path=fcurve_data_path, index=index, action_group=group_name)

                fcurve_map[group_name][path][index] = fcurve

        section_found = False
        for keyframe_section in keyframe_dict:
            for frame_data in keyframe_section:
                frame_number = frame_data["frame"]
                if action.frame_start <= frame_number <= action.frame_end:
                    section_found = True
                    position_field = frame_data.get("position")
                    rotation_field = frame_data.get("rotation")
                    scale_field = frame_data.get("scale")
                    if position_field is not None:
                        last_position = room_scale * Vector(flip(position_field))

                    if rotation_field is not None:
                        last_rotation = Quaternion(flip(rotation_field))

                    if scale_field is not None:
                        last_scale = Vector(flip(scale_field))

                    if is_bone:
                        transform_matrix = node_transform.inverted() @ Matrix.LocRotScale(last_position, last_rotation, last_scale)
                    else:
                        transform_matrix = Matrix.LocRotScale(last_position, last_rotation, last_scale)
                    loc, rot_quat, scl = transform_matrix.decompose()
                    rot_euler = rot_quat.to_euler('XYZ')
                    for i in range(3):
                        fcurve_map[group_name]['location'][i].keyframe_points.insert(frame_number, loc[i], options={'FAST'})
                        fcurve_map[group_name]['scale'][i].keyframe_points.insert(frame_number, scl[i], options={'FAST'})
                        fcurve_map[group_name]['rotation_quaternion'][i].keyframe_points.insert(frame_number, rot_quat[i], options={'FAST'})
                        fcurve_map[group_name]['rotation_euler'][i].keyframe_points.insert(frame_number, rot_euler[i], options={'FAST'})

                    fcurve_map[group_name]['rotation_quaternion'][3].keyframe_points.insert(frame_number, rot_quat[3], options={'FAST'})

        if not section_found and not is_bone:
            # This is specifically for objects since objects with no keys on a frame will have their transform reset instead of stick like bones - Gen
            frame_number = action.frame_start
            if is_bone:
                transform_matrix = Matrix.LocRotScale(last_position, last_rotation, last_scale)
            else:
                transform_matrix = node_transform

            loc, rot_quat, scl = transform_matrix.decompose()
            rot_euler = rot_quat.to_euler('XYZ')
            for i in range(3):
                fcurve_map[group_name]['location'][i].keyframe_points.insert(frame_number, loc[i], options={'FAST'})
                fcurve_map[group_name]['scale'][i].keyframe_points.insert(frame_number, scl[i], options={'FAST'})
                fcurve_map[group_name]['rotation_quaternion'][i].keyframe_points.insert(frame_number, rot_quat[i], options={'FAST'})
                fcurve_map[group_name]['rotation_euler'][i].keyframe_points.insert(frame_number, rot_euler[i], options={'FAST'})

            fcurve_map[group_name]['rotation_quaternion'][3].keyframe_points.insert(frame_number, rot_quat[3], options={'FAST'})

def parse_kv_string(s):
    if not s:
        return s

    result = {}
    found_kv = False

    for line in s.splitlines():
        line = line.strip()
        if not line:
            continue

        if "=" not in line:
            continue

        found_kv = True
        key, value = line.split("=", 1)
        value = value.strip()
        if " " in value:
            parts = value.split()
            parsed = []
            for p in parts:
                try:
                    parsed.append(int(p))
                except ValueError:
                    try:
                        parsed.append(float(p))
                    except ValueError:
                        parsed.append(p)
            result[key] = parsed
        else:
            try:
                result[key] = int(value)
            except ValueError:
                try:
                    result[key] = float(value)
                except ValueError:
                    result[key] = value

    if not found_kv:
        return {"classname": s.strip()}

    return result

def get_bone_distance(node, parent_ob, room_scale):
    child_nodes = node["nodes"]
    child_node_count = len(child_nodes)
    bone_distance = 0
    if child_node_count == 0 and parent_ob:
        if isinstance(parent_ob, bpy.types.EditBone):
            bone_distance = parent_ob.length
        else:
            bone_distance = parent_ob.location.length

    elif child_node_count == 1:
        child_position = Vector(child_nodes[0]["position"])
        position = Vector(node["position"])

        bone_distance = (room_scale * (position - child_position)).length

    elif child_node_count > 1:
        positions = []
        for child_node in child_nodes:
            positions.append(Vector(child_node["position"]))

        average_position = (sum(positions, Vector()) / len(positions))
        position = Vector(node["position"])
        bone_distance = (room_scale * (position - average_position)).length

    if bone_distance < 0.000001:
        bone_distance = room_scale

    return bone_distance

def import_node_recursive(context, data, node, material_list, room_scale, armature=None, strips=None, has_skeleton=False, use_light_radius=True, parent_ob=None, last_mesh=None, is_simple=False, bm=None, ob_data=None, bm_transform=None, world_transform=None):
    has_skin = bool(node.get("bones"))
    has_key = node.get("key") is not None
    has_mesh = node.get("mesh") is not None
    generated_mesh = False

    result = parse_kv_string(node["name"])
    if is_simple:
        if has_mesh:
            node_transform = Matrix.LocRotScale(room_scale * Vector(flip(node["position"])), Quaternion(flip(node["rotation"])), Vector(flip(node["scale"])))
            if bm_transform is not None:
                bm_transform = bm_transform @ node_transform
            else:
                bm_transform = node_transform

            mesh_data = import_mesh(room_scale, node["mesh"], material_list, is_simple, ob_data)
            mesh_data.transform(bm_transform)
            bm.from_mesh(mesh_data)
            bpy.data.meshes.remove(mesh_data)

        for child_node in node["nodes"]:
            import_node_recursive(context, data, child_node, material_list, room_scale, is_simple=is_simple, bm=bm, ob_data=ob_data, bm_transform=bm_transform)

    else:
        if has_skin or has_key or armature:
            if armature is None:
                armature_data = bpy.data.armatures.new(result["classname"])
                armature = object_mesh =  bpy.data.objects.new(result["classname"], armature_data)
                context.collection.objects.link(armature)

                context.view_layer.objects.active = armature

                armature.cb.object_type = str(ObjectType.exclude.value)

                node_transform = Matrix.LocRotScale(room_scale * Vector(flip(node["position"])), Quaternion(flip(node["rotation"])), Vector(flip(node["scale"])))
                if parent_ob is not None:
                    armature.parent = parent_ob

                armature.matrix_local = node_transform

                if last_mesh:
                    bpy.context.view_layer.update()
                    armature_modifier = last_mesh.modifiers.new("Armature", type='ARMATURE')
                    armature_modifier.object = armature
                    last_mesh.parent = armature
                    last_mesh.matrix_parent_inverse = armature.matrix_world.inverted()

                for child_node in data["nodes"]:
                    child_has_anim = child_node.get("anim") is not None
                    child_has_sequence = child_node.get("sequences") is not None
                    if child_has_sequence:
                        anim_dict = child_node["anim"]
                        context.scene.frame_end = anim_dict["frames"]
                        context.scene.render.fps = int(anim_dict["fps"])

                        anim_data = armature.animation_data_create()
                        anim_data.action = None
                        track = anim_data.nla_tracks.new()
                        track.name = armature.name

                        sequences_dict = child_node["sequences"]
                        for sequence_element in sequences_dict:
                            action = bpy.data.actions.new(name="%s_%s" % (armature.name, sequence_element["name"]))
                            action.use_frame_range = True
                            action.frame_start = sequence_element["start"]
                            action.frame_end = sequence_element["end"]

                            strip = track.strips.new(name=action.name, start=int(action.frame_start), action=action)
                            if sequence_element["start"] == sequence_element["end"]:
                                strip.frame_end = sequence_element["start"] + 0.1
                                #strip.action_frame_end = sequence_element["start"] - 0.9

                            strips.append(strip)

                    elif child_has_anim:
                        anim_dict = child_node["anim"]
                        context.scene.frame_end = anim_dict["frames"]

                        anim_data = armature.animation_data_create()
                        anim_data.action = None
                        track = anim_data.nla_tracks.new()
                        track.name = armature.name

                        action = bpy.data.actions.new(name="%s_animation" % armature.name)
                        action.use_frame_range = True
                        action.frame_start = 1
                        action.frame_end = child_node["anim"]["frames"]
                        context.scene.render.fps = int(anim_dict["fps"])

                        strip = track.strips.new(name=action.name, start=int(action.frame_start), action=action)
                        if action.frame_start == action.frame_end:
                            strip.frame_end = action.frame_start + 0.1
                            #strip.action_frame_end = sequence_element["start"] - 0.9

                        strips.append(strip)
                    break

                bpy.ops.object.mode_set(mode='EDIT')

            else:
                object_mesh = armature.data.edit_bones.new(node["name"])
                object_mesh.length = room_scale

                node_transform = Matrix.LocRotScale(room_scale * Vector(flip(node["position"])), Quaternion(flip(node["rotation"])), Vector(flip(node["scale"])))
                if parent_ob is not None:
                    if isinstance(parent_ob, bpy.types.EditBone):
                        object_mesh.parent = parent_ob
                        object_mesh.matrix = parent_ob.matrix @ node_transform
                    else:
                        loc, rot, scl = armature.matrix_world.inverted().decompose()
                        object_mesh.matrix = node_transform

                object_mesh.length = get_bone_distance(node, parent_ob, room_scale)

        else:
            if result["classname"].lower().startswith("brush"):
                generated_mesh = True

                mesh_data = None
                if node.get("mesh"):
                    mesh_data = import_mesh(room_scale, node["mesh"], material_list)

                object_mesh = bpy.data.objects.new(result["classname"], mesh_data)
                context.collection.objects.link(object_mesh)

                object_mesh.cb.object_type = str(ObjectType.mesh.value)

            elif result["classname"].lower().startswith("terrainsector"):
                generated_mesh = True

                mesh_data = None
                if node.get("mesh"):
                    mesh_data = import_mesh(room_scale, node["mesh"], material_list)

                object_mesh = bpy.data.objects.new(result["classname"], mesh_data)
                context.collection.objects.link(object_mesh)

                object_mesh.cb.object_type = str(ObjectType.mesh.value)

            elif result["classname"].lower().startswith("terrain"):
                generated_mesh = True

                mesh_data = None
                if node.get("mesh"):
                    mesh_data = import_mesh(room_scale, node["mesh"], material_list)

                object_mesh = bpy.data.objects.new(result["classname"], mesh_data)
                context.collection.objects.link(object_mesh)

                object_mesh.cb.object_type = str(ObjectType.mesh.value)

            elif result["classname"].lower().startswith("mesh"):
                generated_mesh = True

                mesh_data = None
                if node.get("mesh"):
                    mesh_data = import_mesh(room_scale, node["mesh"], material_list)

                object_mesh = bpy.data.objects.new(result["classname"], mesh_data)
                context.collection.objects.link(object_mesh)

                object_mesh.cb.object_type = str(ObjectType.mesh.value)

            elif result["classname"].lower().startswith("field_hit"):
                generated_mesh = True

                mesh_data = None
                if node.get("mesh"):
                    mesh_data = import_mesh(room_scale, node["mesh"], material_list)

                object_mesh = bpy.data.objects.new(result["classname"], mesh_data)
                context.collection.objects.link(object_mesh)

                object_mesh.cb.object_type = str(ObjectType.mesh.value)

            elif result["classname"] == "light":
                light_data = bpy.data.lights.new(result["classname"], "POINT")
                object_mesh = bpy.data.objects.new(result["classname"], light_data)
                context.collection.objects.link(object_mesh)

                r, g, b = result["color"]
                light_data.color = (r / 255, g / 255, b / 255)
                object_mesh.cb.linear_falloff = result["linearfalloff"]

                if use_light_radius:
                    light_data.shadow_soft_size = room_scale * result["range"]
                    light_data.energy = result["intensity"]
                    light_data.normalize = False
                else:
                    light_data.shadow_soft_size = 0
                    light_data.energy = result["intensity"] * (room_scale * result["range"])
                    light_data.normalize = False

                object_mesh.cb.object_type = str(ObjectType.entity_light.value)

            elif result["classname"] == "spotlight":
                spotlight_data = bpy.data.lights.new(result["classname"], "SPOT")
                object_mesh = bpy.data.objects.new(result["classname"], spotlight_data)
                context.collection.objects.link(object_mesh)

                r, g, b = result["color"]
                spotlight_data.color = (r / 255, g / 255, b / 255)

                outer_deg: float = max(1.0, min(180.0, result["outerconeangle"]))
                inner_deg: float = max(1.0, min(180.0, result["innerconeangle"]))
                ratio = inner_deg / outer_deg if outer_deg > 0.0 else 1.0

                spotlight_data.spot_size = radians(outer_deg)
                spotlight_data.spot_blend = max(0.0, min(1.0, 1.0 - ratio))

                object_mesh.cb.linear_falloff = result["linearfalloff"]

                if use_light_radius:
                    spotlight_data.shadow_soft_size = room_scale * result["range"]
                    spotlight_data.energy = result["intensity"]
                    spotlight_data.normalize = False
                else:
                    spotlight_data.shadow_soft_size = 0
                    spotlight_data.energy = result["intensity"] * (room_scale * result["range"])
                    spotlight_data.normalize = False

                object_mesh.cb.object_type = str(ObjectType.entity_spotlight.value)

            elif result["classname"] == "sunlight":
                sunlight_data = bpy.data.lights.new(result["classname"], "SUN")
                object_mesh = bpy.data.objects.new(result["classname"], sunlight_data)
                context.collection.objects.link(object_mesh)

                object_mesh.cb.object_type = str(ObjectType.exclude.value)

            elif result["classname"].startswith("soundemitter"):
                speaker_data = bpy.data.speakers.new(result["classname"])
                object_mesh = bpy.data.objects.new(result["classname"], speaker_data)
                context.collection.objects.link(object_mesh)

                object_mesh.cb.sound_emitter_id = result["sound"]
                object_mesh.data.distance_max = result["range"]

                object_mesh.cb.object_type = str(ObjectType.entity_sound_emitter.value)

            elif result["classname"].startswith("waypoint"):
                object_mesh = bpy.data.objects.new(result["classname"], None)
                context.collection.objects.link(object_mesh)

                object_mesh.cb.object_type = str(ObjectType.entity_waypoint.value)

            else:
                if not generated_mesh and has_mesh and not has_skeleton:
                    generated_mesh = True
                    mesh_data = import_mesh(room_scale, node["mesh"], material_list)
                    object_mesh = bpy.data.objects.new(node["name"], mesh_data)
                    context.collection.objects.link(object_mesh)
                    object_mesh.cb.object_type = str(ObjectType.mesh.value)
                else:
                    object_mesh = bpy.data.objects.new(result["classname"], None)
                    object_mesh.empty_display_size = room_scale

                    context.collection.objects.link(object_mesh)
                    object_mesh.cb.object_type = str(ObjectType.exclude.value)

            node_transform = Matrix.LocRotScale(room_scale * Vector(flip(node["position"])), Quaternion(flip(node["rotation"])), Vector(flip(node["scale"])))
            if parent_ob is not None:
                object_mesh.parent = parent_ob

            object_mesh.matrix_local = node_transform

        if not generated_mesh and has_mesh:
            generated_mesh = True
            mesh_data = import_mesh(room_scale, node["mesh"], material_list)
            last_mesh = bpy.data.objects.new(node["name"], mesh_data)
            context.collection.objects.link(last_mesh)

            if armature:
                last_mesh.parent = armature
                armature_modifier = last_mesh.modifiers.new("Armature", type='ARMATURE')
                armature_modifier.object = armature
            elif parent_ob:
                last_mesh.parent = parent_ob

            last_mesh.cb.object_type = str(ObjectType.mesh.value)

            node_transform = Matrix.LocRotScale(room_scale * Vector(flip(node["position"])), Quaternion(flip(node["rotation"])), Vector(flip(node["scale"])))
            last_mesh.matrix_local = node_transform

        if has_skin and len(node["bones"]) > 0:
            group_name = object_mesh.name
            if not group_name in last_mesh.vertex_groups.keys():
                last_mesh.vertex_groups.new(name = group_name)

            group_index = last_mesh.vertex_groups.keys().index(group_name)
            for bone_element in node["bones"]:
                last_mesh.vertex_groups[group_index].add([bone_element["vertex_idx"]], bone_element["weight"], 'ADD')

        if has_key:
            import_fcurve_data(room_scale, armature, strips, object_mesh.name, node["key"], node_transform, isinstance(object_mesh, bpy.types.EditBone))

        if world_transform is None:
            world_transform = node_transform

        world_transform = world_transform @ node_transform

        for child_node in node["nodes"]:
            import_node_recursive(context, data, child_node, material_list, room_scale, armature, strips, has_skeleton, use_light_radius, object_mesh, last_mesh, world_transform=world_transform)

def get_mesh(b3d_data, ob, depsgraph, room_scale, armature_ob=None):
    ob_eval = ob.evaluated_get(depsgraph)
    mesh = ob_eval.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
    mesh.calc_loop_triangles()
    if armature_ob is not None:
        # If there is an armature then any mesh data is being moved to the root and we need to apply the transform to make sure it visually stays the same. - Gen
        mesh.transform(ob.matrix_world)

    uv_layer_count = len(mesh.uv_layers)
    color_layer_count = len(mesh.color_attributes)
    layer_uv_0 = mesh.uv_layers.get("uvmap_render")
    layer_uv_1 = mesh.uv_layers.get("uvmap_lightmap")
    layer_color = mesh.color_attributes.get("color")
    layer_alpha = mesh.color_attributes.get("alpha")
    if uv_layer_count > 0 and not layer_uv_0:
        layer_uv_0 = mesh.uv_layers[0]
    if uv_layer_count > 1 and not layer_uv_1:
        layer_uv_1 = mesh.uv_layers[1]
    if color_layer_count > 0 and not layer_color:
        layer_color = mesh.color_attributes[0]
    if color_layer_count > 1 and not layer_alpha:
        layer_alpha = mesh.color_attributes[1]

    mesh_dict = {
        "brush_id": -1,
        "vertices": [],
        "normals": [],
        "rgba": [],
        "uvs": [],
        "faces": []
    }

    vertex_group_count = len(ob.vertex_groups)
    skin_info = {}
    material_map = {}
    vertex_map = {}
    for tri in mesh.loop_triangles:
        mat_name = get_material_name(ob, tri)
        material_dict_idx = -1
        for mat_idx, b3d_material_dict in enumerate(b3d_data["materials"]):
            if mat_name == b3d_material_dict["name"]:
                material_dict_idx = mat_idx
                break

        if material_dict_idx == -1:
            texture_id_list = []
            mat_r = mat_g = mat_b = mat_a = 1.0
            mat_shine = 0
            mat_blend_type = 0
            mat_fx = 0

            scene_mat = bpy.data.materials.get(mat_name)
            if scene_mat and scene_mat.use_nodes:
                lightmap_node = None
                diffuse_node = None

                output_material_node = get_output_material_node(scene_mat)
                bdsf_principled = get_linked_node(output_material_node, "Surface", "BSDF_PRINCIPLED")
                node_group = get_linked_node(output_material_node, "Surface", "GROUP")
                if node_group and node_group.node_tree.name in SHADER_NODE_NAMES:
                    lightmap_node = get_linked_node(node_group, "Light Map", "TEX_IMAGE")
                    diffuse_node = get_linked_node(node_group, "Diffuse Map", "TEX_IMAGE")

                    mat_r, mat_g, mat_b, mat_a = node_group.inputs["Diffuse Overlay"].default_value
                    mat_shine = node_group.inputs["Shine"].default_value
                    mat_blend_type = node_group.inputs["Blend Type"].default_value
                    mat_fx = 0
                    if node_group.inputs["Full Bright"].default_value:
                        mat_fx += MaterialFXFlags.full_bright.value
                    if node_group.inputs["Use Vertex Colors Instead Of Brush Color"].default_value:
                        mat_fx += MaterialFXFlags.use_vertex_colors_instead_of_brush_color.value
                    if node_group.inputs["Flat Shaded"].default_value:
                        mat_fx += MaterialFXFlags.flatshaded.value
                    if node_group.inputs["Disable Fog"].default_value:
                        mat_fx += MaterialFXFlags.disable_fog.value
                    if node_group.inputs["Disable Backface Culling"].default_value:
                        mat_fx += MaterialFXFlags.disable_backface_culling.value
                    if node_group.inputs["Use Vertex Color Alpha As Transparency"].default_value:
                        mat_fx += MaterialFXFlags.use_vertex_color_alpha_as_transparency.value

                elif bdsf_principled:
                    lightmap_node = None
                    diffuse_node = get_linked_node(bdsf_principled, "Base Color", "TEX_IMAGE")
                    for node in scene_mat.node_tree.nodes:
                        if node.type == 'TEX_IMAGE':
                            image = node.image
                            if not image:
                                continue

                            if image.filepath:
                                filename = os.path.basename(bpy.path.abspath(image.filepath))
                                name_no_ext = os.path.splitext(filename)[0]
                                if "_lm" in name_no_ext.lower():
                                    lightmap_node = node
                                    break

                    mat_r, mat_g, mat_b, mat_a = bdsf_principled.inputs[0].default_value # Ignore the alpha from here.
                    mat_a = bdsf_principled.inputs[4].default_value
                    mat_shine = bdsf_principled.inputs[13].default_value
                    mat_blend_type = 1

                texture_entries = [lightmap_node, diffuse_node]
                for texture_entry_idx, texture_entry in enumerate(texture_entries):
                    is_lightmap = False
                    if texture_entry_idx == 0:
                        is_lightmap = True

                    image_name = ""
                    texture_dict_idx = -1
                    if not texture_entry:
                        layer_uv = layer_uv_0
                        if is_lightmap:
                            layer_uv = layer_uv_1

                        if layer_uv is not None:
                            texture_id_list.append(texture_dict_idx)

                        continue

                    mapping_node = get_linked_node(texture_entry, "Vector", "MAPPING")
                    tx = ty = tz = 0.0
                    sx = sy = sz = 1.0
                    rx = ry = rz = 0.0
                    if mapping_node is not None:
                        tx, ty, tz = mapping_node.inputs["Location"].default_value
                        sx, sy, sz = mapping_node.inputs["Scale"].default_value
                        rx, ry, rz = mapping_node.inputs["Rotation"].default_value

                    img = texture_entry.image
                    if img and img.source == 'FILE' and img.filepath:
                        image_name = os.path.basename(bpy.path.abspath(img.filepath))
                        for tex_idx, texture_dict in enumerate(b3d_data["textures"]):
                            txd, tyd = texture_dict["position"]
                            sxd, syd = texture_dict["scale"]
                            rxd = texture_dict["rotation"]

                            if image_name != texture_dict["name"]:
                                continue
                            if (tx, ty) != (txd, tyd):
                                continue
                            if (sx, sy) != (sxd, syd):
                                continue
                            if degrees(rx) != rxd:
                                continue

                            texture_dict_idx = tex_idx

                    if texture_dict_idx == -1:
                        fx = 0
                        if img.cb.color:
                            fx += TextureFXFlags.color.value
                        if img.cb.alpha:
                            fx += TextureFXFlags.alpha.value
                        if img.cb.masked:
                            fx += TextureFXFlags.masked.value
                        if img.cb.mipmapped:
                            fx += TextureFXFlags.mipmapped.value
                        if img.cb.clamp_u:
                            fx += TextureFXFlags.clamp_u.value
                        if img.cb.clamp_v:
                            fx += TextureFXFlags.clamp_v.value
                        if img.cb.spherical_environment_map:
                            fx += TextureFXFlags.spherical_environment_map.value
                        if img.cb.cubic_environment_map:
                            fx += TextureFXFlags.cubic_environment_map.value
                        if img.cb.store_texture_in_vram:
                            fx += TextureFXFlags.store_texture_in_vram.value
                        if img.cb.force_high_color_textures:
                            fx += TextureFXFlags.force_high_color_textures.value
                        if is_lightmap:
                            fx += TextureFXFlags.uses_lightmap_uv.value

                        texture_dict = {
                            "name": image_name,
                            "flags": fx,
                            "blend": img.cb.blend_type,
                            "position": [tx, ty],
                            "scale": [sx, sy],
                            "rotation": degrees(rx)
                        }

                        get_image_properties(img, texture_dict)
                        b3d_data["textures"].append(texture_dict)
                        texture_id = len(b3d_data["textures"]) - 1
                        texture_dict_idx = texture_id

                    texture_id_list.append(texture_dict_idx)

            if len(texture_id_list) == 0:
                texture_id_list.append(-1)

            material_dict = {
                "name": mat_name,
                "rgba": [
                    mat_r,
                    mat_g,
                    mat_b,
                    mat_a
                ],
                "shine": mat_shine,
                "blend": mat_blend_type,
                "fx": mat_fx,
                "tids": texture_id_list
            }

            b3d_data["materials"].append(material_dict)
            material_dict_idx = len(b3d_data["materials"]) - 1

        tri_indices = []
        for loop_index in tri.loops:
            mat_index = tri.material_index

            loop = mesh.loops[loop_index]
            v = mesh.vertices[loop.vertex_index]
            x, y, z = (1.0 / room_scale) * v.co
            i, j, k = loop.normal
            pos = (x, z, y)
            loop_normal = (i, k, j)

            uv_render = (0.0, 0.0)
            uv_lightmap = (0.0, 0.0)
            if layer_uv_0:
                u0, v0 = layer_uv_0.data[loop_index].uv
                uv_render = (u0, 1 - v0)

            if layer_uv_1:
                u1, v1 = layer_uv_1.data[loop_index].uv
                uv_lightmap = (u1, 1 - v1)

            color = (1, 1, 1, 1)
            if layer_color:
                if layer_color.domain == 'POINT':
                    r, g, b, a = layer_color.data[loop.vertex_index].color
                elif layer_color.domain == 'CORNER':
                    r, g, b, a = layer_color.data[loop_index].color
                
                color = (r, g, b, a)
                if layer_alpha:
                    # If someone uses color in a greyscale channel that's their own damn fault.
                    if layer_color.domain == 'POINT':
                        ar, ag, ab, aa = layer_alpha.data[loop.vertex_index].color
                    elif layer_color.domain == 'CORNER':
                        ar, ag, ab, aa = layer_alpha.data[loop_index].color
                        
                    color = (r, g, b, ar)

            v_skins = set()
            for vertex_group in v.groups:
                group_index = vertex_group.group
                weight = vertex_group.weight
                v_skins.add((group_index, weight))

            key = (mat_index, round(pos[0], 6), round(pos[1], 6), round(pos[2], 6), uv_render, uv_lightmap, color, loop_normal)
            if key not in vertex_map:
                vertex_map_index = len(mesh_dict["vertices"])
                vertex_map[key] = vertex_map_index
                mesh_dict["vertices"].append(pos)
                mesh_dict["uvs"].append((*uv_render, *uv_lightmap))
                mesh_dict["normals"].append(loop_normal)
                mesh_dict["rgba"].append(color)
                for vertex_group in v.groups:
                    group_index = vertex_group.group
                    weight = vertex_group.weight
                    if vertex_group_count > group_index and weight > 0.0:
                            group_name = ob.vertex_groups[group_index].name
                            skin_group = skin_info.get(group_name)
                            if skin_group is None:
                                skin_group = skin_info[group_name] = []

                            skin_group.append({"vertex_idx": vertex_map_index, "weight": weight})

            tri_indices.append(vertex_map[key])

        material_section = material_map.get(mat_name)
        if material_section is None:
            material_section = material_map[mat_name] = {"brush_id": material_dict_idx, "indices": []}

        material_section["indices"].append(tri_indices[::-1])

    for mat_key in material_map.keys():
        mesh_dict["faces"].append(material_map[mat_key])

    ob_eval.to_mesh_clear()

    return skin_info, mesh_dict

def get_scene_bones(b3d_data, node_dict, depsgraph, room_scale, skin_info=None, key_info=None, armature=None, parent_ob=None):
    for bone in armature.data.bones:
        if bone.parent == parent_ob:
            node_transform = bone.matrix_local
            if parent_ob is not None:
                node_transform = parent_ob.matrix_local.inverted() @ bone.matrix_local
            loc, rot_quat, scl = node_transform.decompose()

            tx, ty, tz = (1.0 / room_scale) * loc
            sx, sy, sz = scl
            rw, ri, rj, rk = rot_quat
            ob_node_dict = {
                "name": bone.name,
                "position": [
                    tx,
                    tz,
                    ty
                ],
                "scale": [
                    sx,
                    sz,
                    sy
                ],
                "rotation": [
                    rw,
                    ri,
                    rk,
                    rj
                ],
                "nodes": []
            }

            ob_node_dict["bones"] = []
            if skin_info is not None:
                skin_keys = skin_info.keys()
                for skin_key in skin_keys:
                    if bone.name == skin_key:
                        ob_node_dict["bones"] = skin_info[skin_key]

            key_data = key_info.get(bone.name)
            if key_data is not None:
                ob_node_dict["key"] = []
                for action_group in key_data:
                    action_entry = []
                    for frame_data in action_group:
                        frame_index, frame_transform = frame_data

                        f_loc, f_rot_quat, f_scl = frame_transform.decompose()

                        f_tx, f_ty, f_tz = (1.0 / room_scale) * f_loc
                        f_sx, f_sy, f_sz = f_scl
                        f_rw, f_ri, f_rj, f_rk = f_rot_quat

                        key_dict = {
                            "frame": frame_index,
                            "position": [
                                f_tx,
                                f_tz,
                                f_ty
                            ],
                            "scale": [
                                f_sx,
                                f_sz,
                                f_sy
                            ],
                            "rotation": [
                                f_rw,
                                f_ri,
                                f_rk,
                                f_rj
                            ],
                        }
                        action_entry.append(key_dict)

                    ob_node_dict["key"].append(action_entry)


            get_scene_bones(b3d_data, ob_node_dict["nodes"], depsgraph, room_scale, skin_info, key_info, armature, bone)

            node_dict.append(ob_node_dict)

def get_node_name(ob, room_scale):
    node_name = ob.name.lower()
    object_type_enum = ObjectType(int(ob.cb.object_type))
    # The classname bit seems to be something 3D World Studio sets for certain objects and isn't special for the game at all.
    # Going through the effort of preserving it for the sake of the importer. - Gen
    if "brush" in node_name:
        node_name = "classname=brush"
    elif "terrainsector" in node_name:
        node_name = "classname=terrainsector"
    elif "terrain" in node_name:
        node_name = "classname=terrain"
    elif "mesh" in node_name:
        node_name = "classname=mesh"
    elif "field_hit" in node_name:
        node_name = "classname=field_hit"
    elif object_type_enum == ObjectType.entity_light:
        r, g, b = ob.data.color

        light_color = "color=%s %s %s" % (int(r * 255), int(g * 255), int(b * 255))
        light_range = "range=%s" % ((1.0 / room_scale) * ob.data.shadow_soft_size)
        light_intensity = "intensity=%s" % ob.data.energy
        light_linear_falloff = "linearfalloff=%s" % int(ob.cb.linear_falloff)
        node_name = "classname=light\r\n%s\r\n%s\r\n%s\r\n%s" % (light_color, light_intensity, light_range, light_linear_falloff)
    elif object_type_enum == ObjectType.entity_spotlight:
        r, g, b = ob.data.color
        outer_deg = degrees(ob.data.spot_size)

        light_angles = "angles=%s %s %s" % (0, 0, 0)
        light_color = "color=%s %s %s" % (int(r * 255), int(g * 255), int(b * 255))
        light_range = "range=%s" % ((1.0 / room_scale) * ob.data.shadow_soft_size)
        light_intensity = "intensity=%s" % ob.data.energy
        light_inner_cone_angle = "innerconeangle=%s" % int(ob.data.spot_blend * outer_deg)
        light_outer_cone_angle = "outerconeangle=%s" % int(outer_deg)
        light_linear_falloff = "linearfalloff=%s" % int(ob.cb.linear_falloff)

        node_name = "classname=spotlight\r\n%s\r\n%s\r\n%s\r\n%s\r\n%s\r\n%s\r\n%s" % (light_angles, light_color, light_intensity, light_range, light_inner_cone_angle, light_outer_cone_angle, light_linear_falloff)
    elif object_type_enum == ObjectType.entity_sound_emitter:
        sound_id_str = "sound=%s" % ob.cb.sound_emitter_id
        range_str = "range=%s" % ob.data.distance_max
        node_name = "classname=soundemitter\r\n%s\r\n%s" % (sound_id_str, range_str)
    elif object_type_enum == ObjectType.entity_waypoint:
        node_name = "classname=waypoint"

    return node_name

def get_scene_objects(context, b3d_data, node_dict, depsgraph, skin_info, key_info, armature_ob, room_scale, parent_ob=None):
    for ob in bpy.data.objects:
        if ob.parent == parent_ob:
            if ob.type == "MESH" and armature_ob is not None and ob.parent == armature_ob:
                continue

            transform_matrix = ob.matrix_local
            loc, rot_quat, scl = transform_matrix.decompose()

            node_name = get_node_name(ob, room_scale)

            tx, ty, tz = (1.0 / room_scale) * loc
            sx, sy, sz = scl
            rw, ri, rj, rk = rot_quat
            ob_node_dict = {
                "name": node_name,
                "position": [
                    tx,
                    tz,
                    ty
                ],
                "scale": [
                    sx,
                    sz,
                    sy
                ],
                "rotation": [
                    rw,
                    ri,
                    rk,
                    rj
                ],
                "nodes": []
            }

            if armature_ob:
                if ob.type == "ARMATURE":
                    ob_node_dict["bones"] = []
                    get_scene_bones(b3d_data, ob_node_dict["nodes"], depsgraph, room_scale, skin_info, key_info, ob)

                key_data = key_info.get(ob.name)
                if key_data is not None:
                    ob_node_dict["key"] = []
                    for action_group in key_data:
                        action_entry = []
                        for frame_data in action_group:
                            frame_index, frame_transform = frame_data

                            f_loc, f_rot_quat, f_scl = frame_transform.decompose()

                            f_tx, f_ty, f_tz = (1.0 / room_scale) * f_loc
                            f_sx, f_sy, f_sz = f_scl
                            f_rw, f_ri, f_rj, f_rk = f_rot_quat
                            key_dict = {
                                "frame": frame_index,
                                "position": [
                                    f_tx,
                                    f_tz,
                                    f_ty
                                ],
                                "scale": [
                                    f_sx,
                                    f_sz,
                                    f_sy
                                ],
                                "rotation": [
                                    f_rw,
                                    f_ri,
                                    f_rk,
                                    f_rj
                                ],
                            }

                            action_entry.append(key_dict)

                        ob_node_dict["key"].append(action_entry)

            else:
                if ob.type == "MESH":
                    skin_info, mesh_dict = get_mesh(b3d_data, ob, depsgraph, room_scale)
                    ob_node_dict["mesh"] = mesh_dict

            get_scene_objects(context, b3d_data, ob_node_dict["nodes"], depsgraph, skin_info, key_info, armature_ob, room_scale, ob)

            node_dict.append(ob_node_dict)

def set_image_properties(img, texture_dict):
    if img:
        img_b3d = img.cb

        tex_flags = TextureFXFlags(texture_dict["flags"])

        if TextureFXFlags.color in tex_flags:
            img_b3d.color = True
        if TextureFXFlags.alpha in tex_flags:
            img_b3d.alpha = True
        if TextureFXFlags.masked in tex_flags:
            img_b3d.masked = True
        if TextureFXFlags.mipmapped in tex_flags:
            img_b3d.mipmapped = True
        if TextureFXFlags.clamp_u in tex_flags:
            img_b3d.clamp_u = True
        if TextureFXFlags.clamp_v in tex_flags:
            img_b3d.clamp_v = True
        if TextureFXFlags.spherical_environment_map in tex_flags:
            img_b3d.spherical_environment_map = True
        if TextureFXFlags.cubic_environment_map in tex_flags:
            img_b3d.cubic_environment_map = True
        if TextureFXFlags.store_texture_in_vram in tex_flags:
            img_b3d.store_texture_in_vram = True
        if TextureFXFlags.force_high_color_textures in tex_flags:
            img_b3d.force_high_color_textures = True

        img_b3d.blend_type = str(texture_dict["blend"])

def set_material_properties(b3d_node, material_dict):
    if b3d_node:
        mat_flags = MaterialFXFlags(material_dict["fx"])

        if MaterialFXFlags.full_bright in mat_flags:
            b3d_node.inputs["Full Bright"].default_value = True
        if MaterialFXFlags.use_vertex_colors_instead_of_brush_color in mat_flags:
            b3d_node.inputs["Use Vertex Colors Instead Of Brush Color"].default_value = True
        if MaterialFXFlags.flatshaded in mat_flags:
            b3d_node.inputs["Flat Shaded"].default_value = True
        if MaterialFXFlags.disable_fog in mat_flags:
            b3d_node.inputs["Disable Fog"].default_value = True
        if MaterialFXFlags.disable_backface_culling in mat_flags:
            b3d_node.inputs["Disable Backface Culling"].default_value = True
        if MaterialFXFlags.use_vertex_color_alpha_as_transparency in mat_flags:
            b3d_node.inputs["Use Vertex Color Alpha As Transparency"].default_value = True

        b3d_node.inputs["Use Overlay"].default_value = True
        b3d_node.inputs["Use Shine"].default_value = True
        b3d_node.inputs["Blend Type"].default_value = material_dict["blend"]
        b3d_node.inputs["Shine"].default_value = material_dict["shine"]
        b3d_node.inputs["Diffuse Overlay"].default_value = material_dict["rgba"]

def get_image_properties(img, texture_dict):
    img_b3d = img.cb

    tex_flags = 0
    if img_b3d.color:
        tex_flags += TextureFXFlags.color.value
    if img_b3d.alpha:
        tex_flags += TextureFXFlags.alpha.value
    if img_b3d.masked:
        tex_flags += TextureFXFlags.masked.value
    if img_b3d.mipmapped:
        tex_flags += TextureFXFlags.mipmapped.value
    if img_b3d.clamp_u:
        tex_flags += TextureFXFlags.clamp_u.value
    if img_b3d.clamp_v:
        tex_flags += TextureFXFlags.clamp_v.value
    if img_b3d.spherical_environment_map:
        tex_flags += TextureFXFlags.spherical_environment_map.value
    if img_b3d.cubic_environment_map:
        tex_flags += TextureFXFlags.cubic_environment_map.value
    if img_b3d.store_texture_in_vram:
        tex_flags += TextureFXFlags.store_texture_in_vram.value
    if img_b3d.force_high_color_textures:
        tex_flags += TextureFXFlags.force_high_color_textures.value

    texture_dict["flags"] = tex_flags
    texture_dict["blend"] = int(img_b3d.blend_type)

def gather_keyframe_data(context, armature, node_data):
    if not armature.animation_data:
        return

    scene = context.scene
    original_frame = scene.frame_current
    original_action = armature.animation_data.action

    nla_track = next(
        (t for t in armature.animation_data.nla_tracks if t.name == armature.name and not t.mute),
        None
    )
    if not nla_track:
        return

    node_names = {armature.name}
    if armature.pose:
        node_names.update(b.name for b in armature.pose.bones)
    for n in node_names:
        node_data.setdefault(n, [])

    for strip in nla_track.strips:
        if not strip.action:
            continue

        frame_start = int(strip.frame_start)
        frame_end = int(strip.frame_end)
        strip_results = {name: [] for name in node_names}

        for frame in range(frame_start, frame_end + 1):
            scene.frame_set(frame)
            depsgraph = context.evaluated_depsgraph_get()
            eval_arm = armature.evaluated_get(depsgraph)

            for node_name in node_names:
                if node_name == armature.name:
                    loc = eval_arm.location.copy()
                    rot = (
                        eval_arm.rotation_quaternion.copy()
                        if eval_arm.rotation_mode == 'QUATERNION'
                        else eval_arm.rotation_euler.to_quaternion()
                    )
                    scale = eval_arm.scale.copy()
                    mat = Matrix.LocRotScale(loc, rot, scale)
                else:
                    pose_bone = eval_arm.pose.bones.get(node_name)
                    if not pose_bone:
                        continue
                    if pose_bone.parent:
                        mat = pose_bone.parent.matrix.inverted() @ pose_bone.matrix
                    else:
                        mat = pose_bone.matrix.copy()

                strip_results[node_name].append((frame, mat))

        for node_name in node_names:
            node_data[node_name].append(strip_results[node_name])

    armature.animation_data.action = original_action
    scene.frame_set(original_frame)

def export_scene(context, filepath, report):
    room_scale = bpy.context.preferences.addons[__package__].preferences.room_scale
    active_ob = context.view_layer.objects.active
    if active_ob is not None:
        bpy.ops.object.mode_set(mode='OBJECT')

    depsgraph = context.evaluated_depsgraph_get()

    b3d_data = {"nodes": [], "textures": [], "materials": []}

    armature_ob = None
    skin_info = None
    mesh_dict = None
    key_dict = defaultdict(list)
    for node_ob in bpy.data.objects:
        if node_ob.type == "MESH" and node_ob.parent and node_ob.parent.type == "ARMATURE" and node_ob.parent.animation_data is not None and node_ob.parent.animation_data.nla_tracks is not None:
            armature_ob = node_ob.parent

            armature_ob.data.pose_position = 'REST'
            depsgraph.update()

            skin_info, mesh_dict = get_mesh(b3d_data, node_ob, depsgraph, armature_ob)

            armature_ob.data.pose_position = 'POSE'
            depsgraph.update()

        elif node_ob.type == "ARMATURE":
            gather_keyframe_data(context, node_ob, key_dict)

    get_scene_objects(context, b3d_data, b3d_data["nodes"], depsgraph, skin_info, key_dict, armature_ob, room_scale)

    if armature_ob and len(b3d_data["nodes"]) > 0:
        root_node = b3d_data["nodes"][0]
        if mesh_dict is not None:
            tx, tz, ty = root_node["position"]
            sx, sz, sy = root_node["scale"]
            rw, ri, rk, rj = root_node["rotation"]
            root_transform = Matrix.LocRotScale(Vector((tx, ty, tz)),  Quaternion((rw, ri, rj, rk)), Vector((sx, sy, sz))).inverted()
            for v_idx, vertex in enumerate(mesh_dict["vertices"]):
                mtx, mtz, mty = vertex
                mtx, mty, mtz = root_transform @ Vector((mtx, mty, mtz))

                mesh_dict["vertices"][v_idx] = (mtx, mtz, mty)

            for n_idx, normal in enumerate(mesh_dict["normals"]):
                mni, mnk, mnj = normal
                normal_matrix = root_transform.to_3x3().transposed()
                world_normal = normal_matrix @ Vector((mni, mnj, mnk))
                world_normal.normalize()
                mni, mnj, mnk = world_normal

                mesh_dict["normals"][n_idx] = (mni, mnk, mnj)

            root_node["mesh"] = mesh_dict

        for nla_track in armature_ob.animation_data.nla_tracks:
            if nla_track.name == armature_ob.name:
                flags = 0
                frame_end = int(context.scene.frame_end)
                fps = int(context.scene.render.fps)

                root_node["anim"] = {"flags": flags, "frames": frame_end, "fps": fps}
                root_node["sequences"] = []
                for strip in nla_track.strips:
                    strip_name = strip.action.name.replace("%s_" % armature_ob.name, "")
                    start_frame = floor(strip.frame_start)
                    end_frame = floor(strip.frame_end)
                    flags = 0
                    strip_dict = {"name": strip_name, "start": start_frame, "end": end_frame, "flags": flags}
                    root_node["sequences"].append(strip_dict)

    write_b3d(filepath, b3d_data)

    report({'INFO'}, "Export completed successfully")
    return {'FINISHED'}

def find_bones(node, bone_check_list, uv_counts):
    mesh_dict = node.get("mesh")
    bone_check_list.append(bool(node.get("bones")))
    if mesh_dict is not None:
        for uv_channel in mesh_dict["uvs"]:
            uv_counts.append(len(uv_channel))

    for child_node in node["nodes"]:
        find_bones(child_node, bone_check_list, uv_counts)

def import_scene(context, filepath, fullbright_materials, use_light_radius, report, bm=None, ob_data=None, is_simple=False, error_log=None, random_color_gen=None):
    game_path = Path(bpy.context.preferences.addons[__package__].preferences.game_path)
    room_scale = bpy.context.preferences.addons[__package__].preferences.room_scale

    local_asset_path = ""
    if not is_string_empty(str(game_path)) and str(filepath).startswith(str(game_path)):
        local_asset_path = os.path.dirname(os.path.relpath(str(filepath), str(game_path)))

    data = B3DTree().parse(filepath)

    if error_log is None:
        error_log = set()
    if random_color_gen is None:
        random_color_gen = RandomColorGenerator() # generates a random sequence of colors

    material_list = []
    texture_count = 0

    has_skeleton = False
    bone_check_list = []
    uv_counts = []
    for child_node in data["nodes"]:
        find_bones(child_node, bone_check_list, uv_counts)

    texture_dict = data.get("textures")
    material_dict = data.get("materials")
    if texture_dict is not None:
        texture_count = len(texture_dict)

    if material_dict is not None:
        for material_dict in data["materials"]:
            material = bpy.data.materials.new(material_dict["name"])
            material.diffuse_color = random_color_gen.next()

            material.use_nodes = True
            material.node_tree.nodes.clear()

            output_material_node = get_output_material_node(material)
            output_material_node.location = Vector((0.0, 0.0))

            b3d_node = get_shader_node(material.node_tree, SHADER_RESOURCES, "cb_material")
            b3d_node.name = "B3D Material"
            b3d_node.location = (-440.0, 0.0)
            set_material_properties(b3d_node, material_dict)

            connect_inputs(material.node_tree, b3d_node, "Shader", output_material_node, "Surface")

            if fullbright_materials:
                b3d_node.inputs["Is Fullbright"].default_value = True

            mat_flags = MaterialFXFlags(material_dict["fx"])
            if MaterialFXFlags.use_vertex_color_alpha_as_transparency in mat_flags:
                attr_node = material.node_tree.nodes.new("ShaderNodeVertexColor")
                attr_node.location = (-720.0, 0)

                connect_inputs(material.node_tree, attr_node, "Color", b3d_node, "Diffuse Map Alpha")
                material.surface_render_method = 'BLENDED'
                attr_node.layer_name = "alpha"


            valid_texture_id_count = 0
            for tid_element in material_dict["tids"]:
                if tid_element != -1 and texture_count > tid_element:
                    valid_texture_id_count += 1

            for tex_idx, tid_element in enumerate(material_dict["tids"]):
                if tid_element != -1 and texture_count > tid_element:
                    texture = data["textures"][tid_element]
                    tex_name_lowered = texture['name'].lower()
                    if tex_name_lowered.endswith("bump") or tex_name_lowered.endswith("glow"):
                        continue

                    texture_type = TextureTypeEnum.diffuse
                    tex_flags = TextureFXFlags(texture["flags"])
                    if TextureFXFlags.uses_lightmap_uv in tex_flags:
                        texture_type = TextureTypeEnum.lightmap

                    mat_blend = MaterialBlendEnum(material_dict["blend"])

                    texture_asset = get_file(os.path.basename(texture['name']), True, True, directory_path=local_asset_path)
                    if texture_asset:
                        set_image_properties(texture_asset, texture)

                        texture_node = material.node_tree.nodes.new('ShaderNodeTexImage')
                        texture_node.image = texture_asset

                        if texture_type == TextureTypeEnum.lightmap:
                            texture_node.location = (-720.0, 0)
                            connect_inputs(material.node_tree, texture_node, "Color", b3d_node, "Light Map")

                            mapping_node, uv_node = generate_texture_mapping(material.node_tree, texture_node)
                            uv_node.uv_map = "uvmap_lightmap"
                            mapping_node.vector_type = 'TEXTURE'

                            tx, ty = texture["position"]
                            sx, sy = texture["scale"]
                            rx = texture["rotation"]
                            mapping_node.inputs["Location"].default_value = (tx, ty, 0)
                            mapping_node.inputs["Scale"].default_value = (sx, sy, 1)
                            mapping_node.inputs["Rotation"].default_value = (radians(rx), 0, 0)


                        elif texture_type == TextureTypeEnum.diffuse:
                            texture_node.location = (-720.0, -380)
                            connect_inputs(material.node_tree, texture_node, "Color", b3d_node, "Diffuse Map")
                            if mat_blend == MaterialBlendEnum.alpha:
                                connect_inputs(material.node_tree, texture_node, "Alpha", b3d_node, "Diffuse Map Alpha")

                            mapping_node, uv_node = generate_texture_mapping(material.node_tree, texture_node)
                            uv_node.uv_map = "uvmap_render"
                            mapping_node.vector_type = 'TEXTURE'

                            tx, ty = texture["position"]
                            sx, sy = texture["scale"]
                            rx = texture["rotation"]
                            mapping_node.inputs["Location"].default_value = (tx, ty, 0)
                            mapping_node.inputs["Scale"].default_value = (sx, sy, 1)
                            mapping_node.inputs["Rotation"].default_value = (radians(rx), 0, 0)

                            texture_name = os.path.basename(texture['name']).rsplit(".", 1)[0]
                            texture_bump_data = get_file("%sbump" % texture_name, directory_path=local_asset_path)
                            texture_glow_data = get_file("%sglow" % texture_name, directory_path=local_asset_path)
                            if texture_bump_data:
                                texture_bump = material.node_tree.nodes.new("ShaderNodeTexImage")
                                texture_bump.image = texture_bump_data
                                texture_bump.image.alpha_mode = 'CHANNEL_PACKED'
                                texture_bump.interpolation = 'Cubic'
                                texture_bump.image.colorspace_settings.name = 'Non-Color'
                                texture_bump.location = (-720.0, -760)
                                connect_inputs(material.node_tree, texture_bump, "Color", b3d_node, "Normal Map")

                                mapping_node, uv_node = generate_texture_mapping(material.node_tree, texture_bump)
                                uv_node.uv_map = "uvmap_render"
                                mapping_node.vector_type = 'TEXTURE'

                                tx, ty = texture["position"]
                                sx, sy = texture["scale"]
                                rx = texture["rotation"]
                                mapping_node.inputs["Location"].default_value = (tx, ty, 0)
                                mapping_node.inputs["Scale"].default_value = (sx, sy, 1)
                                mapping_node.inputs["Rotation"].default_value = (radians(rx), 0, 0)

                            if texture_glow_data:
                                texture_glow = material.node_tree.nodes.new("ShaderNodeTexImage")
                                texture_glow.image = texture_glow_data
                                texture_glow.image.alpha_mode = 'CHANNEL_PACKED'
                                texture_glow.location = (-720.0, -1140)
                                connect_inputs(material.node_tree, texture_glow, "Color", b3d_node, "Emission Map")

                                mapping_node, uv_node = generate_texture_mapping(material.node_tree, texture_glow)
                                uv_node.uv_map = "uvmap_render"
                                mapping_node.vector_type = 'TEXTURE'

                                tx, ty = texture["position"]
                                sx, sy = texture["scale"]
                                rx = texture["rotation"]
                                mapping_node.inputs["Location"].default_value = (tx, ty, 0)
                                mapping_node.inputs["Scale"].default_value = (sx, sy, 1)
                                mapping_node.inputs["Rotation"].default_value = (radians(rx), 0, 0)

            material_list.append(material)

    strips = []
    armature_ob = None
    for has_bone in bone_check_list:
        if has_bone:
            has_skeleton = True
            break

    for child_node in data["nodes"]:
        import_node_recursive(context, data, child_node, material_list, room_scale, armature_ob, strips, has_skeleton, use_light_radius, is_simple=is_simple, bm=bm, ob_data=ob_data)

    if not is_simple:
        if context.view_layer.objects.active is not None:
            bpy.ops.object.mode_set(mode='OBJECT')

        for error in error_log:
            report({'WARNING'}, error)

    report({'INFO'}, "Import completed successfully")
    return {'FINISHED'}
