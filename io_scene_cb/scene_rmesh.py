import re
import os
import bpy
import bmesh
import configparser

from pathlib import Path
from math import radians, degrees
from .scene_x import import_scene as import_x
from .scene_b3d import import_scene as import_b3d
from mathutils import Matrix, Vector, Euler, Quaternion
from .object_helper import create_door, DoorType, ButtonType, DoorState
from .process_rmesh import TextureType, write_rmesh, read_rmesh, ImportFileType, ExportFileType
from .common_functions import (RandomColorGenerator,
                               ObjectType,
                               MaterialType,
                               linear_to_gamma,
                               gamma_to_linear,
                               get_referenced_collection,
                               get_file,
                               is_string_empty,
                               get_material_name,
                               get_linked_node,
                               connect_inputs,
                               get_output_material_node,
                               flip,
                               get_shader_node,
                               generate_texture_mapping,
                               SHADER_RESOURCES,
                               SHADER_NODE_NAMES)

MIN_BUTTON_LENGTH = 0.01

def update_object(context, report):
    ob = context.object
    ob_type = ObjectType(int(ob.cb.object_type))
    if ob_type == ObjectType.entity_model:
        model_path = bpy.path.abspath(ob.cb.model_path)
        if os.path.isfile(model_path):
            ob.data.clear_geometry()
            ob.data.materials.clear()

            bm = bmesh.new()
            is_simple=True
            if model_path.lower().endswith(".b3d"):
                import_b3d(context, Path(model_path), True, True, "0", True, report, bm, ob.data, is_simple)

            else:
                import_x(context, Path(model_path), True, report, bm, ob.data, is_simple)

            bm.to_mesh(ob.data)
            bm.free()

        else:
            report({'WARNING'}, 'Model path does not point to a valid file.')

    elif ob_type == ObjectType.entity_item:
        game_path = Path(bpy.context.preferences.addons[__package__].preferences.game_path)

        items_ini_path = os.path.join(game_path, r"Data\items.ini")
        if os.path.isfile(items_ini_path):
            items_ini = configparser.ConfigParser()
            items_ini.read(items_ini_path)

            model_name = ob.cb.item_name
            if model_name == "misc":
                model_name = "playingcard"
            elif model_name == "paper":
                model_name = "doc079"
            elif model_name == "vest":
                model_name = "vest"
            elif model_name == "hazmat":
                model_name = "hazmatsuit"
            elif model_name == "nav":
                model_name = "snav"

            item_entry = items_ini.get(model_name, "model", fallback=None)
            if item_entry:
                model_path = get_file(item_entry, False)
                if os.path.isfile(model_path):
                    ob.data.clear_geometry()
                    ob.data.materials.clear()

                    bm = bmesh.new()
                    is_simple=True
                    if model_path.lower().endswith(".b3d"):
                        import_b3d(context, Path(model_path), True, True, "0", True, report, bm, ob.data, is_simple)

                    else:
                        import_x(context, Path(model_path), True, report, bm, ob.data, is_simple)

                    bm.to_mesh(ob.data)
                    bm.free()

                else:
                    report({'WARNING'}, 'Model path does not point to a valid file.')

            else:
                report({'WARNING'}, 'Unable to find a matching model entry in items.ini.')

        else:
            report({'WARNING'}, 'Unable to find a valid items.ini.')

    elif ob_type == ObjectType.entity_door:
        entity_collection = get_referenced_collection("entities", context.scene.collection, False)

        door_type = DoorType(int(ob.cb.door_type))
        door_state = DoorState(ob.cb.start_open)
        door_halved = ob.cb.delete_half

        button_type = ButtonType.normal
        if ob.cb.key_card_level < 0:
            button_type = ButtonType.scanner
        elif len(ob.cb.keypad_code) > 0:
            button_type = ButtonType.code
        elif ob.cb.key_card_level > 0:
            button_type = ButtonType.keycard

        file_type = ImportFileType.rmesh
        entity_idx = 0
        sd_ob = ob
        sba_ob = ob.cb.button_a_ob
        sbb_ob = ob.cb.button_b_ob

        valid_door_ob = False
        if sd_ob and sd_ob.data:
            valid_door_ob = True
            sd_ob.data.clear_geometry()
            sd_ob.data.materials.clear()

        if sba_ob and sba_ob.data:
            sba_ob.data.clear_geometry()
            sba_ob.data.materials.clear()

        if sbb_ob and sbb_ob.data:
            sbb_ob.data.clear_geometry()
            sbb_ob.data.materials.clear()

        if valid_door_ob:
            door_ob, button_a_ob, button_b_ob = create_door(door_type, button_type, door_state, door_halved, file_type, entity_idx, sd_ob, sba_ob, sbb_ob)
            if not sba_ob:
                entity_collection.objects.link(button_b_ob)
                door_ob.cb.button_a_ob = button_a_ob
                button_a_ob.matrix_world = door_ob.matrix_world @ button_a_ob.matrix_world
            if not sbb_ob:
                entity_collection.objects.link(button_a_ob)
                door_ob.cb.button_b_ob = button_b_ob
                button_b_ob.matrix_world = door_ob.matrix_world @ button_b_ob.matrix_world

        else:
            report({'WARNING'}, 'Object is not a mesh type. Convert active object to a mesh manually and then attempt to update.')

def natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', s)]

axis_swap = Matrix(((1,0,0), (0,0,1), (0,1,0)))
def get_blender_rot(rotation, is_spotlight=False):
    pitch, yaw, roll = rotation

    e = Euler((radians(pitch), -radians(yaw), radians(roll)), 'ZXY')
    q = e.to_quaternion()

    m = q.to_matrix()
    m = axis_swap @ m @ axis_swap.inverted()

    if is_spotlight:
        m = m @ Matrix.Rotation(radians(90), 3, 'X')

    return m.to_quaternion()

def get_blitz_rot(rot, is_spotlight=False):
    m = rot.to_matrix()

    if is_spotlight:
        m = m @ Matrix.Rotation(radians(-90), 3, 'X')

    m = axis_swap.inverted() @ m @ axis_swap

    e = m.to_euler('ZXY')

    pitch = degrees(e.x)
    yaw   = -degrees(e.y)
    roll  = degrees(e.z)

    return (pitch, yaw, roll)

def collect_objects():
    mesh_list = []
    render_list = []
    collision_list = []
    trigger_box_list = []
    entity_list = []

    for ob in bpy.context.view_layer.objects:
        ob_type = ObjectType(int(ob.cb.object_type))
        if ob_type == ObjectType.mesh:
            if ob.type == 'MESH':
                mesh_list.append(ob)
        elif ob_type == ObjectType.render:
            if ob.type == 'MESH':
                render_list.append(ob)
        elif ob_type == ObjectType.collision:
            if ob.type == 'MESH':
                collision_list.append(ob)
        elif ob_type == ObjectType.trigger_box:
            if ob.type == 'MESH':
                trigger_box_list.append(ob)
        elif ob_type == ObjectType.entity_screen:
            entity_list.append(ob)
        elif ob_type == ObjectType.entity_waypoint:
            entity_list.append(ob)
        elif ob_type == ObjectType.entity_light:
            if ob.type == 'LIGHT' and ob.data.type == 'POINT':
                entity_list.append(ob)
        elif ob_type == ObjectType.entity_spotlight:
            if ob.type == 'LIGHT' and ob.data.type == 'SPOT':
                entity_list.append(ob)
        elif ob_type == ObjectType.entity_sound_emitter:
            if ob.type == 'SPEAKER':
                entity_list.append(ob)
        elif ob_type == ObjectType.entity_model:
            entity_list.append(ob)
        elif ob_type == ObjectType.entity_item:
            entity_list.append(ob)
        elif ob_type == ObjectType.entity_door:
            entity_list.append(ob)

    entity_list.sort(key=lambda obj: natural_key(obj.name)) # Doing this cause no idea if the game cares about order for entities. Probably not but better be safe. - Gen

    return mesh_list, render_list, collision_list, trigger_box_list, entity_list

def gather_mesh_data(ob, depsgraph, section_data, file_type, use_lightmap_name_override, room_scale, set_gamma, is_collision=False):
    ob_eval = ob.evaluated_get(depsgraph)
    mesh = ob_eval.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
    mesh.calc_loop_triangles()

    layer_uv_0 = None
    layer_uv_1 = None
    layer_color = None
    if not is_collision:
        uv_layer_count = len(mesh.uv_layers)
        color_layer_count = len(mesh.color_attributes)
        layer_uv_0 = mesh.uv_layers.get("uvmap_render")
        layer_uv_1 = mesh.uv_layers.get("uvmap_lightmap")
        layer_color = mesh.color_attributes.get("color")
        if uv_layer_count > 0 and not layer_uv_0:
            layer_uv_0 = mesh.uv_layers[0]
        if uv_layer_count > 1 and not layer_uv_1:
            layer_uv_1 = mesh.uv_layers[1]
        if color_layer_count > 0 and not layer_color:
            layer_color = mesh.color_attributes[0]

    for tri in mesh.loop_triangles:
        section_name = ob.name
        if not is_collision:
            mat_name = get_material_name(ob, tri)
            
            section_dict = {"textures": [], "vertices": [], "triangles": [], "vertex_map": {}}
            lightmap_texture_dict = {"texture_type": 0, "texture_name": ""}
            diffuse_texture_dict = {"texture_type": 0, "texture_name": ""}

            mat = bpy.data.materials.get(mat_name)
            use_nodes = True
            if bpy.app.version <= (5,0,0):
                use_nodes = mat.use_nodes

            if mat and use_nodes:
                output_material_node = get_output_material_node(mat)
                bdsf_principled = get_linked_node(output_material_node, "Surface", "BSDF_PRINCIPLED")
                node_group = get_linked_node(output_material_node, "Surface", "GROUP")
                if node_group and node_group.node_tree.name in SHADER_NODE_NAMES:
                    lightmap_node = get_linked_node(node_group, "Light Map", "TEX_IMAGE")
                    diffuse_node = get_linked_node(node_group, "Diffuse Map", "TEX_IMAGE")
                    diffuse_alpha_node = get_linked_node(node_group, "Diffuse Map Alpha", "TEX_IMAGE")
                    if lightmap_node is not None:
                        img = lightmap_node.image
                        if img:
                            texture_type_value = TextureType.lightmap.value
                            if file_type == ExportFileType.rmesh_uer2:
                                texture_type_value = TextureType.opaque.value
                            lightmap_texture_dict["texture_type"] = texture_type_value
                            if use_lightmap_name_override and not is_string_empty(ob.cb.lightmap_name_override):
                                lightmap_texture_dict["texture_name"] = "%s.png" % ob.cb.lightmap_name_override
                            elif img.source == 'FILE' and img.filepath:
                                lightmap_texture_dict["texture_name"] = os.path.basename(bpy.path.abspath(img.filepath))
                            elif img.source == 'GENERATED':
                                lightmap_texture_dict["texture_name"] = os.path.basename(bpy.path.abspath(img.name))

                    if diffuse_node is not None:
                        img = diffuse_node.image
                        if img:
                            diffuse_texture_type = TextureType.opaque.value
                            if diffuse_alpha_node is not None:
                                diffuse_texture_type = TextureType.transparent.value
                            diffuse_texture_dict["texture_type"] = diffuse_texture_type
                            if img.source == 'FILE' and img.filepath:
                                diffuse_texture_dict["texture_name"] = os.path.basename(bpy.path.abspath(img.filepath))
                            elif img.source == 'GENERATED':
                                diffuse_texture_dict["texture_name"] = os.path.basename(bpy.path.abspath(img.name))

                elif bdsf_principled:
                    lightmap_type_value = TextureType.lightmap.value
                    if file_type == ExportFileType.rmesh_uer2:
                        lightmap_type_value = TextureType.opaque.value
                    for node in mat.node_tree.nodes:
                        if node.type == 'TEX_IMAGE':
                            img = node.image
                            if not img:
                                continue

                            if img.source == 'FILE' and img.filepath:
                                filename = os.path.basename(bpy.path.abspath(img.filepath))
                                if "_lm" in filename.lower():
                                    lightmap_texture_dict["texture_type"] = lightmap_type_value
                                    lightmap_texture_dict["texture_name"] = filename
                                    if use_lightmap_name_override and not is_string_empty(ob.cb.lightmap_name_override):
                                        lightmap_texture_dict["texture_name"] = "%s.png" % ob.cb.lightmap_name_override
                                    
                                    lightmap_name = lightmap_texture_dict["texture_name"]
                                    break
                            elif img.source == 'GENERATED':
                                filename = os.path.basename(bpy.path.abspath(img.name))
                                if "_lm" in filename.lower():
                                    lightmap_texture_dict["texture_type"] = lightmap_type_value
                                    lightmap_texture_dict["texture_name"] = filename
                                    if use_lightmap_name_override and not is_string_empty(ob.cb.lightmap_name_override):
                                        lightmap_texture_dict["texture_name"] = "%s.png" % ob.cb.lightmap_name_override

                                    lightmap_name = lightmap_texture_dict["texture_name"]
                                    break

                    output_material_node = get_output_material_node(mat)
                    bdsf_principled = get_linked_node(output_material_node, "Surface", "BSDF_PRINCIPLED")
                    image_node_a = get_linked_node(bdsf_principled, "Base Color", "TEX_IMAGE")
                    image_node_b = get_linked_node(bdsf_principled, "Alpha", "TEX_IMAGE")
                    if image_node_a is not None:
                        img_a = image_node_a.image
                        if img_a:
                            diffuse_texture_type = TextureType.opaque.value
                            if image_node_b is not None and image_node_b.image:
                                diffuse_texture_type = TextureType.transparent.value

                            if img_a.source == 'FILE' and img_a.filepath:
                                diffuse_texture_dict["texture_type"] = diffuse_texture_type
                                diffuse_texture_dict["texture_name"] = os.path.basename(bpy.path.abspath(img_a.filepath))
                            elif img_a.source == 'GENERATED':
                                diffuse_texture_dict["texture_type"] = diffuse_texture_type
                                diffuse_texture_dict["texture_name"] = os.path.basename(bpy.path.abspath(img_a.name))


            section_name = "%s_%s_%s" % (lightmap_texture_dict["texture_name"], diffuse_texture_dict["texture_name"], diffuse_texture_dict["texture_type"])
            section_dict["textures"].append(lightmap_texture_dict)
            section_dict["textures"].append(diffuse_texture_dict)
            if section_name not in section_data:
                section_data[section_name] = section_dict

        else:
            if section_name not in section_data:
                section_data[section_name] = {"textures": [], "vertices": [], "triangles": [], "vertex_map": {}}

        mesh_section = section_data[section_name]
        vertex_map = mesh_section["vertex_map"]
        tri_indices = []
        for loop_index in tri.loops:
            mat_index = tri.material_index

            loop = mesh.loops[loop_index]
            v = mesh.vertices[loop.vertex_index]
            i, j, k = loop.normal
            loop_normal = (i, j, k)

            pos = (1.0 / room_scale) * Vector(flip((ob_eval.matrix_world @ v.co)))

            uv_render = (0.0, 0.0)
            uv_lightmap = (0.0, 0.0)
            if layer_uv_0:
                u0, v0 = layer_uv_0.data[loop_index].uv
                uv_render = (u0, 1 - v0)

            if layer_uv_1:
                u1, v1 = layer_uv_1.data[loop_index].uv
                uv_lightmap = (u1, 1 - v1)

            r = 1
            g = 1
            b = 1
            if layer_color:
                if layer_color.domain == 'POINT':
                    r, g, b, a = layer_color.data[loop.vertex_index].color
                elif layer_color.domain == 'CORNER':
                    r, g, b, a = layer_color.data[loop_index].color

                if set_gamma:
                    r = linear_to_gamma(r)
                    g = linear_to_gamma(g)
                    b = linear_to_gamma(b)

            color = (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))

            key = str((mat_index, round(pos.x, 6), round(pos.y, 6), round(pos.z, 6), uv_render, uv_lightmap, color, loop_normal))
            if key not in vertex_map:
                vertex_map[key] = len(mesh_section["vertices"])
                vert_dict = {"position": tuple(pos), "uv_render": uv_render, "uv_lightmap": uv_lightmap, "color": color, "normal": loop_normal}
                mesh_section["vertices"].append(vert_dict)

            tri_indices.append(vertex_map[key])

        mesh_section["triangles"].append({"a": tri_indices[2], "b": tri_indices[1], "c": tri_indices[0]})

    ob_eval.to_mesh_clear()

def export_scene(context, filepath, file_type, use_lightmap_name_override, use_game_rules, report):
    game_path = Path(bpy.context.preferences.addons[__package__].preferences.game_path)
    room_scale = bpy.context.preferences.addons[__package__].preferences.room_scale
    set_gamma = bpy.context.preferences.addons[__package__].preferences.set_gamma

    if context.view_layer.objects.active is not None:
        bpy.ops.object.mode_set(mode='OBJECT')

    mesh_list, render_list, collision_list, trigger_box_list, entity_list = collect_objects()

    file_type = ExportFileType(int(file_type))
    if file_type == ExportFileType.rmesh and len(trigger_box_list) > 0:
        file_type = ExportFileType.rmesh_tb

    rmesh_version = 0
    if file_type == ExportFileType.rmesh or file_type == ExportFileType.rmesh_uer:
        rmesh_file_type = "RoomMesh"
    elif file_type == ExportFileType.rmesh_tb:
        rmesh_file_type = "RoomMesh.HasTriggerBox"
    elif file_type == ExportFileType.rmesh_uer2:
        rmesh_file_type = "RoomMesh2"
    elif file_type == ExportFileType.rmesh_salvage:
        rmesh_file_type = "RM"

    file_extension = ".rmesh"

    filepath = filepath.parent / f"{filepath.stem}{file_extension}"

    rmesh_dict = {
        "rmesh_file_type": rmesh_file_type,
        "rmesh_version": rmesh_version,
        "meshes": [],
        "render_meshes": [],
        "collision_meshes": [],
        "trigger_boxes": [],
        "entities": []
    }

    depsgraph = context.evaluated_depsgraph_get()

    mesh_section_data = {}
    for mesh_ob in mesh_list:
        gather_mesh_data(mesh_ob, depsgraph, mesh_section_data, file_type, use_lightmap_name_override, room_scale, set_gamma)

    for mesh_dict in mesh_section_data.values():
        rmesh_dict["meshes"].append(mesh_dict)

    render_section_data = {}
    for render_ob in render_list:
        gather_mesh_data(render_ob, depsgraph, render_section_data, file_type, use_lightmap_name_override, room_scale, set_gamma)

    for render_dict in render_section_data.values():
        rmesh_dict["render_meshes"].append(render_dict)

    collision_section_data = {}
    for ob in collision_list:
        gather_mesh_data(ob, depsgraph, collision_section_data, file_type, use_lightmap_name_override, room_scale, set_gamma, True)

    for collision_dict in collision_section_data.values():
        rmesh_dict["collision_meshes"].append(collision_dict)

    if file_type == ExportFileType.rmesh_tb or file_type == ExportFileType.rmesh_salvage:
        for ob in trigger_box_list:
            trigger_group = ob.cb.trigger_group
            if is_string_empty(trigger_group):
                trigger_group = "unnamed"

            trigger_entry = None
            for trigger_dict in rmesh_dict["trigger_boxes"]:
                if trigger_dict["name"] == trigger_group:
                    trigger_entry = trigger_dict
                    break

            if trigger_entry is None:
                trigger_entry = {"meshes": [], "name": trigger_group}
                rmesh_dict["trigger_boxes"].append(trigger_entry)

            tb_section_data = {}
            gather_mesh_data(ob, depsgraph, tb_section_data, file_type, use_lightmap_name_override, room_scale, set_gamma, True)

            for tb_dict in tb_section_data.values():
                trigger_entry["meshes"].append(tb_dict)

    for ob in entity_list:
        object_type = ObjectType(int(ob.cb.object_type))
        if object_type == ObjectType.entity_screen:
            loc, rot, scl = ob.matrix_world.decompose()
            entity_dict = {}

            if file_type == ExportFileType.rmesh_uer or file_type == ExportFileType.rmesh_uer2:
                entity_dict["entity_type"] = "save_screen"

            else:
                entity_dict["entity_type"] = "screen"

            entity_dict["texture_name"] = os.path.basename(bpy.path.abspath(ob.cb.texture_path))
            entity_dict["model_name"] = os.path.basename(bpy.path.abspath(ob.cb.model_path))
            entity_dict["position"] = tuple((1.0 / room_scale) * Vector(flip(loc)))
            entity_dict["euler_rotation"] = get_blitz_rot(rot)
            entity_dict["scale"] = flip(scl)

            rmesh_dict["entities"].append(entity_dict)

        elif object_type == ObjectType.entity_waypoint:
            loc, rot, scl = ob.matrix_world.decompose()
            entity_dict = {}

            entity_dict["entity_type"] = "waypoint"
            entity_dict["position"] = tuple((1.0 / room_scale) * Vector(flip(loc)))
            rmesh_dict["entities"].append(entity_dict)

        elif object_type == ObjectType.entity_light:
            if not file_type == ExportFileType.rmesh_uer2 and use_game_rules and not ob.cb.has_sprite:
                continue

            loc, rot, scl = ob.matrix_world.decompose()
            r, g, b = ob.data.color
            entity_dict = {}

            if file_type == ExportFileType.rmesh_uer and ob.cb.is_light_fix:
                entity_dict["entity_type"] = "light_fix"
            else:
                entity_dict["entity_type"] = "light"

            entity_dict["position"] = tuple((1.0 / room_scale) * Vector(flip(loc)))
            entity_dict["color"] = "%s %s %s" % (round(r * 255), round(g * 255), round(b * 255))
            entity_dict["range"] = (1.0 / room_scale) * ob.data.shadow_soft_size
            entity_dict["intensity"] =  ob.data.energy
            if file_type == ExportFileType.rmesh_uer2:
                entity_dict["has_sprite"] = ob.cb.has_sprite
                entity_dict["sprite_scale"] = ob.cb.sprite_scale
                entity_dict["casts_shadows"] = ob.data.use_shadow
                entity_dict["scattering"] = ob.cb.scattering
                entity_dict["ff_array"] = []
                for ff in range(31):
                    entity_dict["ff_array"].append(0)

            rmesh_dict["entities"].append(entity_dict)

        elif object_type == ObjectType.entity_spotlight:
            if not file_type == ExportFileType.rmesh_uer2 and use_game_rules and not ob.cb.has_sprite:
                continue

            loc, rot, scl = ob.matrix_world.decompose()
            r, g, b = ob.data.color
            entity_dict = {}

            entity_dict["entity_type"] = "spotlight"
            entity_dict["position"] = tuple((1.0 / room_scale) * Vector(flip(loc)))
            entity_dict["color"] = "%s %s %s" % (round(r * 255), round(g * 255), round(b * 255))
            entity_dict["range"] = (1.0 / room_scale) * ob.data.shadow_soft_size
            entity_dict["intensity"] =  ob.data.energy

            if file_type == ExportFileType.rmesh_uer2:
                p, y, r = get_blitz_rot(rot, True)
                entity_dict["has_sprite"] = ob.cb.has_sprite
                entity_dict["sprite_scale"] = ob.cb.sprite_scale
                entity_dict["casts_shadows"] = ob.data.use_shadow
                entity_dict["direction"] = [p, y]
                entity_dict["outer_cone_angle"] = degrees(ob.data.spot_size)
                entity_dict["scattering"] = ob.data.spot_blend
                entity_dict["ff_array"] = []
                for ff in range(31):
                    entity_dict["ff_array"].append(0)

            else:
                outer_deg = degrees(ob.data.spot_size)
                p, y, r = get_blitz_rot(rot, True)
                entity_dict["euler_rotation"] = "%s %s %s" % (p, y, r)
                entity_dict["inner_cone_angle"] = int(ob.data.spot_blend * outer_deg)
                entity_dict["outer_cone_angle"] = int(outer_deg)

            rmesh_dict["entities"].append(entity_dict)

        elif object_type == ObjectType.entity_sound_emitter:
            loc, rot, scl = ob.matrix_world.decompose()
            entity_dict = {}

            entity_dict["entity_type"] = "soundemitter"
            entity_dict["position"] = tuple((1.0 / room_scale) * Vector(flip(loc)))
            entity_dict["id"] = int(ob.cb.sound_emitter_id)
            entity_dict["range"] = ob.data.distance_max
            rmesh_dict["entities"].append(entity_dict)

        elif object_type == ObjectType.entity_model:
            loc, rot, scl = ob.matrix_world.decompose()
            entity_dict = {}

            if file_type == ExportFileType.rmesh_uer or file_type == ExportFileType.rmesh_uer2:
                entity_dict["entity_type"] = "mesh"

            else:
                entity_dict["entity_type"] = "model"

            model_name = os.path.basename(bpy.path.abspath(ob.cb.model_path))
            texture_name = ""
            if file_type == ExportFileType.rmesh_uer2:
                model_name = model_name.rsplit(".", 1)[0]
                results = bpy.path.abspath(ob.cb.texture_path).split(str(game_path) + os.sep, 1)
                if len(results) > 1:
                    texture_name = results[1]

            entity_dict["model_name"] = model_name
            entity_dict["texture_name"] = texture_name
            entity_dict["position"] = tuple((1.0 / room_scale) * Vector(flip(loc)))
            entity_dict["euler_rotation"] = get_blitz_rot(rot)
            entity_dict["scale"] = flip(scl)
            entity_dict["has_collision"] = int(ob.cb.has_collision)
            entity_dict["fx"] = ob.cb.fx

            rmesh_dict["entities"].append(entity_dict)

        elif object_type == ObjectType.entity_item:
            loc, rot, scl = ob.matrix_world.decompose()
            entity_dict = {}

            entity_dict["entity_type"] = "item"
            entity_dict["position"] = tuple((1.0 / room_scale) * Vector(flip(loc)))
            entity_dict["item_name"] = ob.cb.item_name
            entity_dict["model_name"] = ob.cb.model_path
            entity_dict["use_custom_rotation"] = ob.cb.use_custom_rotation
            entity_dict["euler_rotation"] = get_blitz_rot(rot)
            entity_dict["state_1"] = ob.cb.state_1
            entity_dict["state_2"] = ob.cb.state_2
            entity_dict["spawn_chance"] = ob.cb.spawn_chance

            rmesh_dict["entities"].append(entity_dict)

        elif object_type == ObjectType.entity_door:
            loc, rot, scl = ob.matrix_world.decompose()
            x, y, z = rot.to_euler()
            entity_dict = {}

            button_scale = Vector((7.68, 7.68, 7.68))
            door_type = DoorType(int(ob.cb.door_type))
            if door_type == DoorType.big:
                ob_a_matrix = Matrix.LocRotScale((1.0 / room_scale) * Vector((432, -192, 179.2)), Euler((0, 0, radians(-90))), button_scale)
                ob_b_matrix = Matrix.LocRotScale((1.0 / room_scale) * Vector((-432, 192, 179.2)), Euler((0, 0, radians(90))), button_scale)
            else:
                ob_a_matrix = Matrix.LocRotScale((1.0 / room_scale) * Vector((153.6, -25.6, 179.2)), Euler((0, 0, 0)), button_scale)
                ob_b_matrix = Matrix.LocRotScale((1.0 / room_scale) * Vector((-153.6, 25.6, 179.2)), Euler((0, 0, radians(180))), button_scale)

            button_1_position = (0, 0, 0)
            button_1_angle = (0, 0, 0)
            button_2_position = (0, 0, 0)
            button_2_angle = (0, 0, 0)
            button_a_ob = ob.cb.button_a_ob
            button_b_ob = ob.cb.button_b_ob
            if button_a_ob:
                local_bam = ob_a_matrix.inverted() @ button_a_ob.matrix_local
                loc_ba, rot_ba, scl_ba = local_bam.decompose()
                if loc_ba.length >= MIN_BUTTON_LENGTH:
                    baw_loc, baw_rot, baw_scl = button_a_ob.matrix_world.decompose()
                    button_1_position = flip((1.0 / room_scale) * baw_loc)

                arx, ary, arz = get_blitz_rot(rot_ba)
                button_1_angle = (round(arx), round(ary), round(arz))

            if button_b_ob:
                local_bbm = ob_b_matrix.inverted() @ button_b_ob.matrix_local
                loc_bb, rot_bb, scl_bb = local_bbm.decompose()
                if loc_bb.length >= MIN_BUTTON_LENGTH:
                    bbw_loc, bbw_rot, bbw_scl = button_a_ob.matrix_world.decompose()
                    button_2_position = flip((1.0 / room_scale) * bbw_loc)

                brx, bry, brz = get_blitz_rot(rot_bb)
                button_2_angle = (round(brx), round(bry), round(brz))

            entity_dict["entity_type"] = "door"
            entity_dict["position"] = tuple((1.0 / room_scale) * Vector(flip(loc)))
            entity_dict["door_type"] = door_type.value
            entity_dict["door_identifier"] = ob.cb.door_identifier
            entity_dict["key_card_level"] = ob.cb.key_card_level
            entity_dict["keypad_code"] = ob.cb.keypad_code
            entity_dict["angle"] = degrees(z)
            entity_dict["start_open"] = ob.cb.start_open
            entity_dict["locked"] = ob.cb.locked
            entity_dict["delete_half"] = ob.cb.delete_half
            entity_dict["allow_scp_079_remote_control"] = ob.cb.allow_scp_079_remote_control
            entity_dict["button_1_position"] = button_1_position
            entity_dict["button_1_angle"] = button_1_angle
            entity_dict["button_2_position"] = button_2_position
            entity_dict["button_2_angle"] = button_2_angle

            rmesh_dict["entities"].append(entity_dict)

    write_rmesh(rmesh_dict, filepath, file_type)

    report({'INFO'}, "Export completed successfully")
    return {'FINISHED'}

def generate_mesh_data(mesh_dict, mesh_data, mesh_idx, local_asset_path, random_color_gen, error_log, file_type, report, fullbright_materials, split_by_material, material_type_enum, room_scale, set_gamma, is_collision=False):
    mesh_name = "temp_mesh"
    if mesh_data is None:
        mesh_name = "mesh"

    mesh = bpy.data.meshes.new("%s_%s" % (mesh_name, mesh_idx))

    vertices = [room_scale * Vector(flip(vertex["position"])) for vertex in mesh_dict["vertices"]]
    triangles = [list(triangle.values())[::-1] for triangle in mesh_dict["triangles"]]
    mesh.from_pydata(vertices, [], triangles)
    mesh.validate(clean_customdata=True)

    if not is_collision:
        mat = bpy.data.materials.new(name="texture_%s" % mesh_idx)
        mat.diffuse_color = random_color_gen.next()
        mesh.materials.append(mat)
        mesh_data.materials.append(mat)

        if bpy.app.version <= (5,0,0):
            mat.use_nodes = True

        mat.node_tree.nodes.clear()

        output_material_node = get_output_material_node(mat)
        output_material_node.location = Vector((0.0, 0.0))

        if material_type_enum == MaterialType.simple:
            bsdf_node = mat.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
            bsdf_node.name = "Principled BSDF"
            bsdf_node.location = (-440.0, 0.0)
            connect_inputs(mat.node_tree, bsdf_node, "BSDF", output_material_node, "Surface")
            
            shader_input_node = bsdf_node
            shader_color_input = "Base Color"
            shader_alpha_input = "Alpha"
            shader_emission_input = "Emission Color"

        else:
            rmesh_node = get_shader_node(mat.node_tree, SHADER_RESOURCES, "cb_material")
            rmesh_node.name = "RMESH Material"
            rmesh_node.location = (-440.0, 0.0)
            connect_inputs(mat.node_tree, rmesh_node, "Shader", output_material_node, "Surface")
            if fullbright_materials:
                rmesh_node.inputs["Is Fullbright"].default_value = True

            shader_input_node = rmesh_node
            shader_color_input = "Diffuse Map"
            shader_alpha_input = "Diffuse Map Alpha"
            shader_emission_input = "Emission Map"

        texture_lightmap = None
        diffuse_type = TextureType.none
        texture_diffuse = None
        for texture_idx, texture_dict in enumerate(mesh_dict["textures"]):
            if texture_idx == 0:
                texture_lightmap_data = get_file(texture_dict["texture_name"], directory_path=local_asset_path)
                if not texture_lightmap_data and not is_string_empty(texture_dict["texture_name"]):
                    if not file_type == ImportFileType.rmesh_uer2:
                        error_log.add('Failed to retrive "%s". Generating blank image' % texture_dict["texture_name"])

                    texture_lightmap_data = bpy.data.images.get(texture_dict["texture_name"])
                    if texture_lightmap_data is None:
                        texture_lightmap_data = bpy.data.images.new(name=texture_dict["texture_name"], width=2, height=2)
                        texture_lightmap_data.generated_color = (1.0, 1.0, 1.0, 1.0)

                if texture_lightmap_data:
                    texture_lightmap = mat.node_tree.nodes.new("ShaderNodeTexImage")
                    texture_lightmap.image = texture_lightmap_data
                    texture_lightmap.image.alpha_mode = 'CHANNEL_PACKED'
                    texture_lightmap.location = (-720.0, -320.0)

                    if not material_type_enum == MaterialType.simple:
                        connect_inputs(mat.node_tree, texture_lightmap, "Color", shader_input_node, "Light Map")

                    mapping_node, uv_node = generate_texture_mapping(mat.node_tree, texture_lightmap)
                    uv_node.uv_map = "uvmap_lightmap"
                    mapping_node.vector_type = 'TEXTURE'

                elif len(texture_dict["texture_name"]) > 0:
                    error_log.add('Failed to retrive "%s"' % texture_dict["texture_name"])

            elif texture_idx == 1:
                diffuse_type = TextureType(texture_dict["texture_type"])
                texture_diffuse_data = get_file(texture_dict["texture_name"], directory_path=local_asset_path)
                if not texture_diffuse_data and not is_string_empty(texture_dict["texture_name"]):
                    error_log.add('Failed to retrive "%s". Generating blank image' % texture_dict["texture_name"])
                    texture_diffuse_data = bpy.data.images.get(texture_dict["texture_name"])
                    if texture_diffuse_data is None:
                        texture_diffuse_data = bpy.data.images.new(name=texture_dict["texture_name"], width=2, height=2)
                        texture_diffuse_data.generated_color = (1.0, 1.0, 1.0, 1.0)

                if texture_diffuse_data:
                    texture_diffuse = mat.node_tree.nodes.new("ShaderNodeTexImage")
                    texture_diffuse.image = texture_diffuse_data
                    texture_diffuse.image.alpha_mode = 'CHANNEL_PACKED'
                    texture_diffuse.location = (-720.0, 0.0)

                    connect_inputs(mat.node_tree, texture_diffuse, "Color", shader_input_node, shader_color_input)
                    if diffuse_type == TextureType.transparent:
                        connect_inputs(mat.node_tree, texture_diffuse, "Alpha", shader_input_node, shader_alpha_input)

                    mapping_node, uv_node = generate_texture_mapping(mat.node_tree, texture_diffuse)
                    uv_node.uv_map = "uvmap_render"
                    mapping_node.vector_type = 'TEXTURE'

                    texture_name = os.path.basename(texture_dict["texture_name"]).rsplit(".", 1)[0]
                    texture_bump_data = get_file("%sbump" % texture_name, directory_path=local_asset_path)
                    texture_glow_data = get_file("%sglow" % texture_name, directory_path=local_asset_path)
                    if texture_bump_data:
                        texture_bump = mat.node_tree.nodes.new("ShaderNodeTexImage")
                        texture_bump.image = texture_bump_data
                        texture_bump.image.alpha_mode = 'CHANNEL_PACKED'
                        texture_bump.interpolation = 'Cubic'
                        texture_bump.image.colorspace_settings.name = 'Non-Color'
                        texture_bump.location = (-720.0, -640.0)

                        if material_type_enum == MaterialType.simple:
                            normal_map_node = mat.node_tree.nodes.new("ShaderNodeNormalMap")
                            normal_map_node.location = (-720.0, -640.0)
                            connect_inputs(mat.node_tree, texture_bump, "Color", normal_map_node, "Color")
                            connect_inputs(mat.node_tree, normal_map_node, "Normal", shader_input_node, "Normal")

                        else:
                            connect_inputs(mat.node_tree, texture_bump, "Color", shader_input_node, "Normal Map")

                        mapping_node, uv_node = generate_texture_mapping(mat.node_tree, texture_bump)
                        uv_node.uv_map = "uvmap_render"
                        mapping_node.vector_type = 'TEXTURE'

                    if texture_glow_data:
                        texture_glow = mat.node_tree.nodes.new("ShaderNodeTexImage")
                        texture_glow.image = texture_glow_data
                        texture_glow.image.alpha_mode = 'CHANNEL_PACKED'
                        texture_glow.location = (-720.0, -1140)

                        connect_inputs(mat.node_tree, texture_glow, "Color", shader_input_node, shader_emission_input)

                        mapping_node, uv_node = generate_texture_mapping(mat.node_tree, texture_glow)
                        uv_node.uv_map = "uvmap_render"
                        mapping_node.vector_type = 'TEXTURE'

            else:
                report({'WARNING'}, 'Texture index out of range: %s' % texture_idx)

        loop_normals = []
        layer_color = mesh.color_attributes.get("color")
        layer_uv_0 = mesh.uv_layers.get("uvmap_render")
        layer_uv_1 = mesh.uv_layers.get("uvmap_lightmap")
        if not layer_color:
            layer_color = mesh.color_attributes.new("color", "BYTE_COLOR", "CORNER")
            mesh.attributes.active_color_name = "color"
            mesh.attributes.render_color_index = 0
        if not layer_uv_0:
            layer_uv_0 = mesh.uv_layers.new(name="uvmap_render")
        if not layer_uv_1:
            layer_uv_1 = mesh.uv_layers.new(name="uvmap_lightmap")

    for poly in mesh.polygons:
        poly.use_smooth = True
        if not is_collision:
            mat_idx = mesh_idx
            if split_by_material:
                mat_idx = 0

            poly.material_index = mat_idx
            for loop_index in poly.loop_indices:
                vert_index = mesh.loops[loop_index].vertex_index
                vertex = mesh_dict["vertices"][vert_index]
                layer_uv_0.data[loop_index].uv = (vertex["uv_render"][0], 1 - vertex["uv_render"][1])
                layer_uv_1.data[loop_index].uv = (vertex["uv_lightmap"][0], 1 - vertex["uv_lightmap"][1])

                r = vertex["color"][0] / 255
                g = vertex["color"][1] / 255
                b = vertex["color"][2] / 255
                if set_gamma:
                    r = gamma_to_linear(r)
                    g = gamma_to_linear(g)
                    b = gamma_to_linear(b)

                layer_color.data[loop_index].color = (r, g, b, 1.0)
                if file_type == ImportFileType.rmesh_uer2:
                    loop_normals.append(Vector(vertex["normal"]))

    if file_type == ImportFileType.rmesh_uer2 and not is_collision:
        mesh.normals_split_custom_set(loop_normals)

    return mesh

def import_scene(context, filepath, file_type, fullbright_materials, use_light_radius, use_game_rules, split_by_material, import_meshes, import_collisions, 
                 import_trigger_boxes, import_entities, report):
    file_type, rmesh_dict = read_rmesh(filepath, ImportFileType(int(file_type)))

    game_path = Path(bpy.context.preferences.addons[__package__].preferences.game_path)
    room_scale = bpy.context.preferences.addons[__package__].preferences.room_scale
    material_type_enum = MaterialType(int(bpy.context.preferences.addons[__package__].preferences.material_type))
    set_gamma = bpy.context.preferences.addons[__package__].preferences.set_gamma

    random_color_gen = RandomColorGenerator() # generates a random sequence of colors

    error_log = set()

    local_asset_path = ""
    local_prop_path = r"GFX\map\Props"
    local_screen_path = r"GFX\screens"
    if file_type == ImportFileType.rmesh_uer or file_type == ImportFileType.rmesh_uer2:
        local_prop_path = r"GFX\Map\Props"
        local_screen_path = r"GFX\Map\Screens"

    if not is_string_empty(str(game_path)) and str(filepath).startswith(str(game_path)):
        local_asset_path = os.path.dirname(os.path.relpath(str(filepath), str(game_path)))

    has_mesh_data = False
    has_collision_data = False
    has_entity_data = False
    for mesh_dict in rmesh_dict["meshes"]:
        if len(mesh_dict["vertices"]) > 0:
            has_mesh_data = True
            break

    for collision_dict in rmesh_dict["collision_meshes"]:
        if len(collision_dict["vertices"]) > 0:
            has_collision_data = True
            break

    if len(rmesh_dict["entities"]) > 0:
        has_entity_data = True

    if has_mesh_data and import_meshes:
        if split_by_material:
            for mesh_idx, mesh_dict in enumerate(rmesh_dict["meshes"]):
                tex_name = ""
                if len(mesh_dict["textures"]) > 1 and mesh_dict["textures"][1]["texture_name"]:
                    tex_name = mesh_dict["textures"][1]["texture_name"]
                elif len(mesh_dict["textures"]) > 0 and mesh_dict["textures"][0]["texture_name"]:
                    tex_name = mesh_dict["textures"][0]["texture_name"]

                obj_name = os.path.splitext(os.path.basename(tex_name))[0] if tex_name else "mesh_%s" % mesh_idx

                single_mesh = bpy.data.meshes.new(obj_name)
                object_mesh = bpy.data.objects.new(obj_name, single_mesh)
                object_mesh.cb.object_type = str(ObjectType.mesh.value)
                context.scene.collection.objects.link(object_mesh)

                bm = bmesh.new()
                temp_mesh = generate_mesh_data(mesh_dict, single_mesh, mesh_idx, local_asset_path, random_color_gen, error_log, file_type, report, fullbright_materials, split_by_material, material_type_enum, room_scale, set_gamma)
                bm.from_mesh(temp_mesh)
                bpy.data.meshes.remove(temp_mesh)
                bm.to_mesh(single_mesh)
                bm.free()

                if single_mesh.materials:
                    single_mesh.materials[0].name = obj_name

                object_mesh.data.attributes.active_color_name = "color"
                object_mesh.data.attributes.render_color_index = 0

        else:
            mesh_collection = get_referenced_collection("meshes", context.scene.collection, False)
            full_mesh = bpy.data.meshes.new("room_mesh")
            object_mesh = bpy.data.objects.new("room_mesh", full_mesh)
            object_mesh.cb.object_type = str(ObjectType.mesh.value)
            mesh_collection.objects.link(object_mesh)

            bm = bmesh.new()
            for mesh_idx, mesh_dict in enumerate(rmesh_dict["meshes"]):
                temp_mesh = generate_mesh_data(mesh_dict, full_mesh, mesh_idx, local_asset_path, random_color_gen, error_log, file_type, report, fullbright_materials, split_by_material, material_type_enum, room_scale, set_gamma)
                bm.from_mesh(temp_mesh)
                bpy.data.meshes.remove(temp_mesh)

            bm.to_mesh(full_mesh)
            bm.free()

            object_mesh.data.attributes.active_color_name = "color"
            object_mesh.data.attributes.render_color_index = 0

    if file_type == ImportFileType.rmesh_salvage:
        has_render_data = False
        for render_dict in rmesh_dict["render_meshes"]:
            if len(render_dict["vertices"]) > 0:
                has_render_data = True
                break

        if has_render_data:
            render_collection = get_referenced_collection("render", context.scene.collection, False)
            render_mesh = bpy.data.meshes.new("room_mesh_render")
            object_render = bpy.data.objects.new("room_mesh_render", render_mesh)
            object_render.cb.object_type = str(ObjectType.render.value)
            render_collection.objects.link(object_render)

            bm = bmesh.new()
            for render_idx, render_dict in enumerate(rmesh_dict["render_meshes"]):
                temp_render = generate_mesh_data(render_dict, render_mesh, render_idx, local_asset_path, random_color_gen, error_log, file_type, report, fullbright_materials, split_by_material, material_type_enum, room_scale, set_gamma)

                bm.from_mesh(temp_render)
                bpy.data.meshes.remove(temp_render)

            bm.to_mesh(render_mesh)
            bm.free()

    if has_collision_data and import_collisions:
        collision_collection = get_referenced_collection("collisions", context.scene.collection, True)
        for collision_idx, collision_dict in enumerate(rmesh_dict["collision_meshes"]):
            collision_mesh = generate_mesh_data(collision_dict, None, collision_idx, local_asset_path, random_color_gen, error_log, file_type, report, fullbright_materials, split_by_material, material_type_enum, room_scale, set_gamma, True)
            collision_ob = bpy.data.objects.new("collision_%s" % collision_idx, collision_mesh)
            collision_ob.cb.object_type = str(ObjectType.collision.value)
            collision_collection.objects.link(collision_ob)

    if (file_type == ImportFileType.rmesh_tb or file_type == ImportFileType.rmesh_salvage) and import_trigger_boxes:
        has_tb_data = False
        for tb_group_dict in rmesh_dict["trigger_boxes"]:
            for tb_dict in tb_group_dict["meshes"]:
                if len(tb_dict["vertices"]) > 0:
                    has_tb_data = True
                    break

        if has_tb_data:
            trigger_box_collection = get_referenced_collection("trigger_boxes", context.scene.collection, True)
            for trigger_box_idx, trigger_box_dict in enumerate(rmesh_dict["trigger_boxes"]):
                for trigger_idx, trigger_dict in enumerate(trigger_box_dict["meshes"]):
                    trigger_name = "trigger_g%st%s" % (trigger_box_idx, trigger_idx)
                    trigger_mesh = generate_mesh_data(trigger_dict, None, trigger_idx, local_asset_path, random_color_gen, error_log, file_type, report, fullbright_materials, split_by_material, material_type_enum, room_scale, set_gamma, True)
                    trigger_mesh_object_mesh = bpy.data.objects.new(trigger_name, trigger_mesh)
                    trigger_mesh_object_mesh.cb.object_type = str(ObjectType.trigger_box.value)
                    trigger_mesh_object_mesh.cb.trigger_group = trigger_box_dict["name"]
                    trigger_box_collection.objects.link(trigger_mesh_object_mesh)

    items_ini = None
    items_ini_path = os.path.join(game_path, r"Data\items.ini")
    if os.path.isfile(items_ini_path):
        items_ini = configparser.ConfigParser()
        items_ini.read(items_ini_path)

    max_sound_emitters_per_room = 8
    sound_emitter_count = 0
    if has_entity_data and import_entities:
        entity_collection = get_referenced_collection("entities", context.scene.collection, False)
        entity_meshes = {}
        for entity_idx, entity_dict in enumerate(rmesh_dict["entities"]):
            if entity_dict["entity_type"] == "screen":
                loc = room_scale * Vector(flip(entity_dict["position"]))
                if use_game_rules and loc.length == 0.0:
                    continue

                object_mesh = bpy.data.objects.new("%s screen" % entity_idx, None)
                object_mesh.cb.object_type = str(ObjectType.entity_screen.value)
                object_mesh.empty_display_type = 'IMAGE'

                file_path = get_file(entity_dict["texture_name"], True, False, local_screen_path)
                if file_path is not None:
                    object_mesh.cb.texture_path = file_path
                    if os.path.isfile(file_path):
                        file_asset = bpy.data.images.load(file_path, check_existing=True)
                        object_mesh.data = file_asset

                entity_collection.objects.link(object_mesh)

                rot = Euler((radians(90), 0, radians(90)))
                scl = Vector((1, 1, 1))
                object_mesh.matrix_world = Matrix.LocRotScale(loc, rot, scl)

            elif entity_dict["entity_type"] == "save_screen":
                object_mesh = bpy.data.objects.new("%s save_screen" % entity_idx, None)
                object_mesh.cb.object_type = str(ObjectType.entity_screen.value)
                entity_collection.objects.link(object_mesh)

                loc = room_scale * Vector(flip(entity_dict["position"]))
                rot = get_blender_rot(entity_dict["euler_rotation"])
                scl = Vector(entity_dict["scale"])
                object_mesh.matrix_world = Matrix.LocRotScale(loc, rot, scl)

                model_path = get_file(entity_dict["model_name"], False)
                texture_path = get_file(entity_dict["texture_name"], True, False)
                object_mesh.cb.is_uer = True
                if model_path is not None:
                    object_mesh.cb.model_path = model_path
                if texture_path is not None:
                    object_mesh.cb.texture_path = texture_path

            elif entity_dict["entity_type"] == "waypoint":
                object_mesh = bpy.data.objects.new("%s waypoint" % entity_idx, None)
                object_mesh.empty_display_size = room_scale * 1
                object_mesh.cb.object_type = str(ObjectType.entity_waypoint.value)
                entity_collection.objects.link(object_mesh)
                loc = room_scale * Vector(flip(entity_dict["position"]))
                rot = Quaternion()
                scl = Vector((1, 1, 1))
                object_mesh.matrix_world = Matrix.LocRotScale(loc, rot, scl)

            elif entity_dict["entity_type"] == "light" or entity_dict["entity_type"] == "light_fix":
                loc = room_scale * Vector(flip(entity_dict["position"]))
                if entity_dict["entity_type"] == "light" and use_game_rules and loc.length == 0.0:
                    continue

                object_data = bpy.data.lights.new("%s light" % entity_idx, "POINT")
                object_mesh = bpy.data.objects.new("%s light" % entity_idx, object_data)
                object_mesh.cb.object_type = str(ObjectType.entity_light.value)
                entity_collection.objects.link(object_mesh)

                rot = Quaternion()
                scl = Vector((1, 1, 1))
                object_mesh.matrix_world = Matrix.LocRotScale(loc, rot, scl)
                if use_light_radius:
                    object_data.shadow_soft_size = room_scale * entity_dict["range"]
                    object_data.energy = entity_dict["intensity"]
                    object_data.normalize = False
                else:
                    object_data.shadow_soft_size = 0
                    object_data.energy = entity_dict["intensity"] * (room_scale * entity_dict["range"])
                    object_data.normalize = False

                r, g, b = entity_dict["color"].split(" ")
                object_data.color = (int(r) / 255, int(g) / 255, int(b) / 255)

                if file_type == ImportFileType.rmesh_uer or file_type == ImportFileType.rmesh_uer2:
                    object_mesh.cb.is_uer = True
                    if entity_dict["entity_type"] == "light_fix":
                        object_mesh.cb.is_light_fix = True

                if file_type == ImportFileType.rmesh_uer2:
                    object_mesh.cb.has_sprite = bool(entity_dict["has_sprite"])
                    object_mesh.cb.sprite_scale = entity_dict["sprite_scale"]
                    object_data.use_shadow = bool(entity_dict["casts_shadows"])
                    object_mesh.cb.scattering = entity_dict["scattering"]

            elif entity_dict["entity_type"] == "spotlight":
                loc = room_scale * Vector(flip(entity_dict["position"]))
                if use_game_rules and loc.length == 0.0:
                    continue

                object_data = bpy.data.lights.new("%s spotlight" % entity_idx, "SPOT")
                object_mesh = bpy.data.objects.new("%s spotlight" % entity_idx, object_data)
                object_mesh.cb.object_type = str(ObjectType.entity_spotlight.value)
                entity_collection.objects.link(object_mesh)
                if use_light_radius:
                    object_data.shadow_soft_size = room_scale * entity_dict["range"]
                    object_data.energy = entity_dict["intensity"]
                    object_data.normalize = False
                else:
                    object_data.shadow_soft_size = 0
                    object_data.energy = entity_dict["intensity"] * (room_scale * entity_dict["range"])
                    object_data.normalize = False

                r, g, b = entity_dict["color"].split(" ")
                object_data.color = (int(r) / 255, int(g) / 255, int(b) / 255)
                if file_type == ImportFileType.rmesh_uer or file_type == ImportFileType.rmesh_uer2:
                    object_mesh.cb.is_uer = True

                if file_type == ImportFileType.rmesh_uer2:
                    object_mesh.cb.has_sprite = bool(entity_dict["has_sprite"])
                    object_mesh.cb.sprite_scale = entity_dict["sprite_scale"]
                    object_data.use_shadow = bool(entity_dict["casts_shadows"])
                    x, y = entity_dict["direction"]

                    rotation = [x, y, 0]
                    object_data.spot_size = radians(entity_dict["outer_cone_angle"])
                    object_data.spot_blend = entity_dict["scattering"]

                else:
                    outer_deg: float = max(1.0, min(180.0, entity_dict["outer_cone_angle"]))
                    inner_deg: float = max(1.0, min(180.0, entity_dict["inner_cone_angle"]))
                    ratio = inner_deg / outer_deg if outer_deg > 0.0 else 1.0

                    object_data.spot_size = radians(outer_deg)
                    object_data.spot_blend = max(0.0, min(1.0, 1.0 - ratio))

                    p, y, r = entity_dict["euler_rotation"].split(" ")
                    rotation = [float(p), float(y), float(r)]

                rot = get_blender_rot(rotation, True)
                scl = Vector((1, 1, 1))
                object_mesh.matrix_world = Matrix.LocRotScale(loc, rot, scl)

            elif entity_dict["entity_type"] == "soundemitter":
                if use_game_rules and sound_emitter_count >= max_sound_emitters_per_room:
                    continue
                else:
                    sound_emitter_count += 1

                speaker_data = bpy.data.speakers.new("%s soundemitter" % entity_idx)
                object_mesh = bpy.data.objects.new("%s soundemitter" % entity_idx, speaker_data)
                object_mesh.cb.object_type = str(ObjectType.entity_sound_emitter.value)
                entity_collection.objects.link(object_mesh)

                loc = room_scale * Vector(flip(entity_dict["position"]))
                rot = Quaternion()
                scl = Vector((1, 1, 1))
                object_mesh.matrix_world = Matrix.LocRotScale(loc, rot, scl)
                object_mesh.cb.sound_emitter_id = str(entity_dict["id"])
                object_mesh.data.distance_max = entity_dict["range"]

            elif entity_dict["entity_type"] == "playerstart":
                object_mesh = bpy.data.objects.new("%s playerstart" % entity_idx, None)
                object_mesh.empty_display_size = room_scale * 1
                object_mesh.cb.object_type = str(ObjectType.exclude.value)
                entity_collection.objects.link(object_mesh)

                loc = room_scale * Vector(flip(entity_dict["position"]))
                rot = get_blender_rot([float(p), float(y), float(r)])
                scl = Vector((1, 1, 1))
                object_mesh.matrix_world = Matrix.LocRotScale(loc, rot, scl)

            elif entity_dict["entity_type"] == "model" or entity_dict["entity_type"] == "mesh":
                is_uer_prop = False
                if entity_dict["entity_type"] == "mesh":
                    is_uer_prop = True

                if not is_uer_prop and use_game_rules and entity_dict["model_name"] == "":
                    continue

                model_path = get_file(entity_dict["model_name"], False, directory_path=local_prop_path)
                texture_path = None
                if is_uer_prop:
                    texture_path = get_file(entity_dict["texture_name"], True, False)

                ob_data = entity_meshes.get(model_path)
                if ob_data is None and model_path:
                    ob_data = entity_meshes[model_path] = bpy.data.meshes.new("%s model" % entity_idx)
                    bm = bmesh.new()
                    is_simple=True
                    if model_path.lower().endswith(".b3d"):
                        import_b3d(context, Path(model_path), fullbright_materials, use_light_radius, "0", True, report, bm, ob_data, is_simple, error_log, random_color_gen)

                    else:
                        import_x(context, Path(model_path), True, report, bm, ob_data, is_simple, error_log, random_color_gen)

                    bm.to_mesh(ob_data)
                    bm.free()

                object_mesh = bpy.data.objects.new("%s %s" % (entity_idx, entity_dict["entity_type"]), ob_data)
                if ob_data is None:
                    object_mesh.empty_display_size = room_scale * 1

                if is_uer_prop:
                    object_mesh.cb.is_uer = True

                object_mesh.cb.object_type = str(ObjectType.entity_model.value)
                if model_path is not None:
                    object_mesh.cb.model_path = model_path

                if texture_path is not None:
                    object_mesh.cb.texture_path = texture_path

                entity_collection.objects.link(object_mesh)
                if not file_type == ImportFileType.rmesh_uer:
                    loc = room_scale * Vector(flip(entity_dict["position"]))
                    rot = get_blender_rot(entity_dict["euler_rotation"])
                    scl = Vector(entity_dict["scale"])
                    object_mesh.matrix_world = Matrix.LocRotScale(loc, rot, scl)

                if is_uer_prop:
                    object_mesh.cb.has_collision = bool(entity_dict["has_collision"])
                    object_mesh.cb.fx = entity_dict["fx"]

            elif entity_dict["entity_type"] == "item":
                ob_data = None
                model_scale = 1
                if items_ini:
                    model_name = entity_dict["model_name"]
                    if model_name == "misc":
                        model_name = "playingcard"
                    elif model_name == "paper":
                        model_name = "doc079"
                    elif model_name == "vest":
                        model_name = "vest"
                    elif model_name == "hazmat":
                        model_name = "hazmatsuit"
                    elif model_name == "nav":
                        model_name = "snav"

                    item_entry = items_ini.get(model_name, "model", fallback=None)
                    if item_entry:
                        model_path = get_file(item_entry, False)
                        ob_data = entity_meshes.get(model_path)
                        if ob_data is None and model_path:
                            ob_data = entity_meshes[model_path] = bpy.data.meshes.new("%s mesh" % entity_idx)
                            bm = bmesh.new()
                            is_simple=True
                            if model_path.lower().endswith(".b3d"):
                                import_b3d(context, Path(model_path), fullbright_materials, use_light_radius, "0", True, report, bm, ob_data, is_simple, error_log, random_color_gen)

                            else:
                                import_x(context, Path(model_path), True, report, bm, ob_data, is_simple, error_log, random_color_gen)

                            bm.to_mesh(ob_data)
                            bm.free()

                object_mesh = bpy.data.objects.new("%s item" % entity_idx, ob_data)
                if ob_data is None:
                    object_mesh.empty_display_size = room_scale * 1

                object_mesh.cb.object_type = str(ObjectType.entity_item.value)
                entity_collection.objects.link(object_mesh)

                loc = room_scale * Vector(flip(entity_dict["position"]))
                rot = get_blender_rot(entity_dict["euler_rotation"])
                scl = Vector((model_scale, model_scale, model_scale))
                object_mesh.matrix_world = Matrix.LocRotScale(loc, rot, scl)
                if file_type == ExportFileType.rmesh or file_type == ExportFileType.rmesh_tb:
                    object_mesh.cb.item_name = entity_dict["item_name"]
                else:
                    object_mesh.cb.item_name = entity_dict["model_name"]
                object_mesh.cb.use_custom_rotation = bool(entity_dict["use_custom_rotation"])
                object_mesh.cb.state_1 = entity_dict["state_1"]
                object_mesh.cb.state_2 = entity_dict["state_2"]
                object_mesh.cb.spawn_chance = entity_dict["spawn_chance"]

            elif entity_dict["entity_type"] == "door":
                door_type = DoorType(entity_dict["door_type"])
                button_type = ButtonType.normal
                if entity_dict["key_card_level"] < 0:
                    button_type = ButtonType.scanner
                elif len(entity_dict["keypad_code"]) > 0:
                    button_type = ButtonType.code
                elif entity_dict["key_card_level"] > 0:
                    button_type = ButtonType.keycard

                door_halved = False
                if file_type == ImportFileType.rmesh_salvage:
                    door_halved = bool(entity_dict["delete_half"])

                door_state = DoorState(entity_dict["start_open"])
                door_ob, button_a_ob, button_b_ob = create_door(door_type, button_type, door_state, door_halved, file_type, entity_idx)
                door_ob.cb.object_type = str(ObjectType.entity_door.value)
                entity_collection.objects.link(door_ob)
                entity_collection.objects.link(button_a_ob)
                entity_collection.objects.link(button_b_ob)

                loc = room_scale * Vector(flip(entity_dict["position"]))
                rot = Euler((0, 0, radians(entity_dict["angle"])))
                scl = Vector((1,1,1))
                door_ob.matrix_world = Matrix.LocRotScale(loc, rot, scl)

                door_ob.cb.door_type = str(entity_dict["door_type"])
                if file_type == ImportFileType.rmesh_salvage and rmesh_dict["rmesh_version"] >= 1:
                    door_ob.cb.door_identifier = entity_dict["door_identifier"]

                door_ob.cb.key_card_level = entity_dict["key_card_level"]
                door_ob.cb.keypad_code = entity_dict["keypad_code"]
                door_ob.cb.start_open = bool(entity_dict["start_open"])
                door_ob.cb.allow_scp_079_remote_control = bool(entity_dict["allow_scp_079_remote_control"])
                door_ob.cb.button_a_ob = button_a_ob
                door_ob.cb.button_b_ob = button_b_ob
                if file_type == ImportFileType.rmesh_salvage:
                    context.view_layer.update()
                    door_ob.cb.locked = bool(entity_dict["locked"])
                    door_ob.cb.delete_half = door_halved

                    loc_result = room_scale * Vector(flip(entity_dict["button_1_position"]))
                    loc_baw, rot_baw, scl_baw = button_a_ob.matrix_world.decompose()
                    if not loc_result.length >= MIN_BUTTON_LENGTH:
                        loc_result = loc_baw

                    rot = get_blender_rot(entity_dict["button_1_angle"])
                    scl = scl_baw
                    button_a_ob.matrix_world = Matrix.LocRotScale(loc_result, rot, scl)

                    loc_result = room_scale * Vector(flip(entity_dict["button_2_position"]))
                    loc_bbw, rot_bbw, scl_bbw = button_b_ob.matrix_world.decompose()
                    if not loc_result.length >= MIN_BUTTON_LENGTH:
                        loc_result = loc_bbw

                    rot = get_blender_rot(entity_dict["button_2_angle"])
                    scl = scl_bbw
                    button_b_ob.matrix_world = Matrix.LocRotScale(loc_result, rot, scl)

            else:
                report({'WARNING'}, "Unknown entity type: %s" % entity_dict["entity_type"])

    for error in error_log:
        report({'WARNING'}, error)

    report({'INFO'}, "Import completed successfully")
    return {'FINISHED'}
