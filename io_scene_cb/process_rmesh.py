from enum import Enum, auto
from .common_functions import (read_string,
                               write_string,
                               read_integer,
                               write_integer,
                               read_byte,
                               write_byte,
                               read_float,
                               write_float,
                               read_vector,
                               write_vector,
                               read_2d_vector,
                               write_2d_vector,
                               read_uv,
                               write_uv,
                               read_color,
                               write_color)

class ImportFileType(Enum):
    rmesh_auto = 0
    rmesh = auto()
    rmesh_tb = auto()
    rmesh_uer = auto()
    rmesh_uer2 = auto()
    rmesh_salvage = auto()

class ExportFileType(Enum):
    rmesh = 0
    rmesh_tb = auto()
    rmesh_uer = auto()
    rmesh_uer2 = auto()
    rmesh_salvage = auto()

class TextureType(Enum):
    none = 0
    opaque = auto()
    lightmap = auto()
    transparent = auto()

def read_mesh_data(rmesh_stream, file_type, section_dict, is_coll=False):
    mesh_count = read_integer(rmesh_stream)
    for mesh_idx in range(mesh_count):
        mesh_dict = {
            "vertices": [],
            "triangles": []
        }
        if not is_coll:
            mesh_dict["textures"] = []

            for texture_idx in range(2):
                texture_dict = {}

                texture_dict["texture_type"] = read_byte(rmesh_stream)
                texture_dict["texture_name"] = ""
                if TextureType(texture_dict["texture_type"]) is not TextureType.none:
                    texture_dict["texture_name"] = read_string(rmesh_stream)

                mesh_dict["textures"].append(texture_dict)

        vertex_count = read_integer(rmesh_stream)
        for vertex_idx in range(vertex_count):
            vertex_dict = {}

            vertex_dict["position"] = read_vector(rmesh_stream)
            if not is_coll:
                vertex_dict["uv_render"] = read_uv(rmesh_stream)
                vertex_dict["uv_lightmap"] = read_uv(rmesh_stream)
                vertex_dict["color"] = read_color(rmesh_stream)
                if file_type == ImportFileType.rmesh_uer2:
                    vertex_dict["normal"] = read_vector(rmesh_stream)

            mesh_dict["vertices"].append(vertex_dict)

        triangle_count = read_integer(rmesh_stream)
        for triangle_idx in range(triangle_count):
            triangle_dict = {}

            triangle_dict["a"] = read_integer(rmesh_stream)
            triangle_dict["b"] = read_integer(rmesh_stream)
            triangle_dict["c"] = read_integer(rmesh_stream)

            mesh_dict["triangles"].append(triangle_dict)

        section_dict.append(mesh_dict)

def read_rmesh(file_path, file_type):
    rmesh_dict = {
        "rmesh_file_type": "",
        "rmesh_version": 0,
        "meshes": [],
        "render_meshes": [],
        "collision_meshes": [],
        "trigger_boxes": [],
        "entities": []
    }
    with file_path.open("rb") as rmesh_stream:
        byte_length = file_path.stat().st_size
        if byte_length > 0:
            return rmesh_dict
            
        rmesh_dict["rmesh_file_type"] = read_string(rmesh_stream)
        if rmesh_dict["rmesh_file_type"] != "RoomMesh" and rmesh_dict["rmesh_file_type"] != "RoomMesh.HasTriggerBox" and rmesh_dict["rmesh_file_type"] != "RoomMesh2" and rmesh_dict["rmesh_file_type"] != "RM":
            raise ValueError('Input file was "%s" instead of "RoomMesh", "RoomMesh.HasTriggerBox", "RoomMesh2", or RM and therefore is not an RMESH file' % rmesh_dict["rmesh_file_type"])

        if file_type == ImportFileType.rmesh_auto:
            if rmesh_dict["rmesh_file_type"] == "RoomMesh":
                file_type = ImportFileType.rmesh

            elif rmesh_dict["rmesh_file_type"] == "RoomMesh.HasTriggerBox":
                file_type = ImportFileType.rmesh_tb

            elif rmesh_dict["rmesh_file_type"] == "RoomMesh2":
                file_type = ImportFileType.rmesh_uer2

            elif rmesh_dict["rmesh_file_type"] == "RM":
                file_type = ImportFileType.rmesh_salvage

        if file_type == ImportFileType.rmesh_salvage:
            rmesh_dict["rmesh_version"] = read_byte(rmesh_stream)

        read_mesh_data(rmesh_stream, file_type, rmesh_dict["meshes"])
        if file_type == ImportFileType.rmesh_salvage:
            read_mesh_data(rmesh_stream, file_type, rmesh_dict["render_meshes"])

        read_mesh_data(rmesh_stream, file_type, rmesh_dict["collision_meshes"], True)

        if file_type == ImportFileType.rmesh_tb or file_type == ImportFileType.rmesh_salvage:
            trigger_box_count = read_integer(rmesh_stream)
            for trigger_box_idx in range(trigger_box_count):
                trigger = {
                    "meshes": [],
                    "name": ""
                }

                read_mesh_data(rmesh_stream, file_type, trigger["meshes"], True)

                trigger["name"] = read_string(rmesh_stream)
                rmesh_dict["trigger_boxes"].append(trigger)

        entity_count = read_integer(rmesh_stream)
        for entity_idx in range(entity_count):
            entity_dict = {}
            entity_dict["entity_type"] = read_string(rmesh_stream)
            if entity_dict["entity_type"] == "screen":
                entity_dict["position"] = read_vector(rmesh_stream)
                entity_dict["texture_name"] = read_string(rmesh_stream)

            elif entity_dict["entity_type"] == "save_screen":
                entity_dict["position"] = read_vector(rmesh_stream)
                entity_dict["model_name"] = read_string(rmesh_stream)
                entity_dict["euler_rotation"] = read_vector(rmesh_stream)
                entity_dict["scale"] = read_vector(rmesh_stream)
                entity_dict["texture_name"] = read_string(rmesh_stream)

            elif entity_dict["entity_type"] == "waypoint":
                entity_dict["position"] = read_vector(rmesh_stream)

            elif entity_dict["entity_type"] == "light":
                entity_dict["position"] = read_vector(rmesh_stream)
                entity_dict["range"] = read_float(rmesh_stream)
                entity_dict["color"] = read_string(rmesh_stream)
                entity_dict["intensity"] = read_float(rmesh_stream)
                if file_type == ImportFileType.rmesh_uer2:
                    entity_dict["has_sprite"] = read_byte(rmesh_stream)
                    entity_dict["sprite_scale"] = read_float(rmesh_stream)
                    entity_dict["casts_shadows"] = read_byte(rmesh_stream)
                    entity_dict["scattering"] = read_float(rmesh_stream)
                    entity_dict["ff_array"] = []
                    for ff in range(31):
                        ff_element = read_integer(rmesh_stream)
                        entity_dict["ff_array"].append(ff_element)

            elif entity_dict["entity_type"] == "light_fix":
                if file_type == ImportFileType.rmesh_uer2:
                    entity_dict["position"] = read_vector(rmesh_stream)
                    entity_dict["range"] = read_float(rmesh_stream)
                    entity_dict["color"] = read_string(rmesh_stream)
                    entity_dict["intensity"] = read_float(rmesh_stream)
                    entity_dict["has_sprite"] = read_byte(rmesh_stream)
                    entity_dict["sprite_scale"] = read_float(rmesh_stream)
                    entity_dict["casts_shadows"] = read_byte(rmesh_stream)
                    entity_dict["scattering"] = read_float(rmesh_stream)
                    entity_dict["ff_array"] = []
                    for ff in range(31):
                        ff_element = read_integer(rmesh_stream)
                        entity_dict["ff_array"].append(ff_element)

                else:
                    entity_dict["position"] = read_vector(rmesh_stream)
                    entity_dict["color"] = read_string(rmesh_stream)
                    entity_dict["intensity"] = read_float(rmesh_stream)
                    entity_dict["range"] = read_float(rmesh_stream)

            elif entity_dict["entity_type"] == "spotlight":
                entity_dict["position"] = read_vector(rmesh_stream)
                entity_dict["range"] = read_float(rmesh_stream)
                entity_dict["color"] = read_string(rmesh_stream)
                entity_dict["intensity"] = read_float(rmesh_stream)
                if file_type == ImportFileType.rmesh_uer2:
                    entity_dict["has_sprite"] = read_byte(rmesh_stream)
                    entity_dict["sprite_scale"] = read_float(rmesh_stream)
                    entity_dict["casts_shadows"] = read_byte(rmesh_stream)
                    entity_dict["direction"] = read_2d_vector(rmesh_stream)
                    entity_dict["outer_cone_angle"] = read_float(rmesh_stream)
                    entity_dict["scattering"] = read_float(rmesh_stream)
                    entity_dict["ff_array"] = []
                    for ff in range(31):
                        ff_element = read_integer(rmesh_stream)
                        entity_dict["ff_array"].append(ff_element)

                else:
                    entity_dict["euler_rotation"] = read_string(rmesh_stream)
                    entity_dict["inner_cone_angle"] = read_integer(rmesh_stream)
                    entity_dict["outer_cone_angle"] = read_integer(rmesh_stream)

            elif entity_dict["entity_type"] == "soundemitter":
                entity_dict["position"] = read_vector(rmesh_stream)
                entity_dict["id"] = read_integer(rmesh_stream)
                entity_dict["range"] = read_float(rmesh_stream)

            elif entity_dict["entity_type"] == "playerstart":
                entity_dict["position"] = read_vector(rmesh_stream)
                entity_dict["euler_rotation"] = read_string(rmesh_stream)

            elif entity_dict["entity_type"] == "model":
                entity_dict["model_name"] = read_string(rmesh_stream)
                if not file_type == ImportFileType.rmesh_uer:
                    entity_dict["position"] = read_vector(rmesh_stream)
                    entity_dict["euler_rotation"] = read_vector(rmesh_stream)
                    entity_dict["scale"] = read_vector(rmesh_stream)

            elif entity_dict["entity_type"] == "mesh":
                entity_dict["position"] = read_vector(rmesh_stream)
                entity_dict["model_name"] = read_string(rmesh_stream)
                entity_dict["euler_rotation"] = read_vector(rmesh_stream)
                entity_dict["scale"] = read_vector(rmesh_stream)
                entity_dict["has_collision"] = read_byte(rmesh_stream)
                entity_dict["fx"] = read_integer(rmesh_stream)
                entity_dict["texture_name"] = read_string(rmesh_stream)

            elif entity_dict["entity_type"] == "item":
                if file_type == ImportFileType.rmesh_salvage:
                    entity_dict["position"] = read_vector(rmesh_stream)
                    entity_dict["model_name"] = read_string(rmesh_stream)
                    entity_dict["use_custom_rotation"] = read_byte(rmesh_stream)
                    entity_dict["euler_rotation"] = read_vector(rmesh_stream)
                    entity_dict["state_1"] = read_float(rmesh_stream)
                    entity_dict["state_2"] = read_float(rmesh_stream)
                    entity_dict["spawn_chance"] = read_float(rmesh_stream)

                else:
                    entity_dict["position"] = read_vector(rmesh_stream)
                    entity_dict["item_name"] = read_string(rmesh_stream)
                    entity_dict["model_name"] = read_string(rmesh_stream)
                    entity_dict["use_custom_rotation"] = read_byte(rmesh_stream)
                    entity_dict["euler_rotation"] = read_vector(rmesh_stream)
                    entity_dict["state_1"] = read_float(rmesh_stream)
                    entity_dict["state_2"] = read_float(rmesh_stream)
                    entity_dict["spawn_chance"] = read_float(rmesh_stream)

            elif entity_dict["entity_type"] == "door":
                if file_type == ImportFileType.rmesh_salvage:
                    entity_dict["position"] = read_vector(rmesh_stream)
                    entity_dict["door_type"] = read_integer(rmesh_stream)
                    if rmesh_dict["rmesh_version"] >= 1:
                        entity_dict["door_identifier"] = read_integer(rmesh_stream)

                    entity_dict["key_card_level"] = read_integer(rmesh_stream)
                    entity_dict["keypad_code"] = read_string(rmesh_stream)
                    entity_dict["angle"] = read_float(rmesh_stream)
                    entity_dict["start_open"] = read_byte(rmesh_stream)
                    entity_dict["locked"] = read_byte(rmesh_stream)
                    entity_dict["delete_half"] = read_byte(rmesh_stream)
                    entity_dict["allow_scp_079_remote_control"] = read_byte(rmesh_stream)
                    entity_dict["button_1_position"] = read_vector(rmesh_stream)
                    entity_dict["button_1_angle"] = read_vector(rmesh_stream)
                    entity_dict["button_2_position"] = read_vector(rmesh_stream)
                    entity_dict["button_2_angle"] = read_vector(rmesh_stream)

                else:
                    entity_dict["position"] = read_vector(rmesh_stream)
                    entity_dict["door_type"] = read_integer(rmesh_stream)
                    entity_dict["key_card_level"] = read_integer(rmesh_stream)
                    entity_dict["keypad_code"] = read_string(rmesh_stream)
                    entity_dict["angle"] = read_float(rmesh_stream)
                    entity_dict["start_open"] = read_byte(rmesh_stream)
                    entity_dict["allow_scp_079_remote_control"] = read_byte(rmesh_stream)

            else:
                print("Unknown entity type: %s" % entity_dict["entity_type"])

            rmesh_dict["entities"].append(entity_dict)

    return file_type, rmesh_dict

def write_mesh_data(rmesh_stream, file_type, section_dict, is_coll=False):
    write_integer(rmesh_stream, len(section_dict))
    for mesh_dict in section_dict:
        if not is_coll:
            for texture_dict in mesh_dict["textures"]:
                write_byte(rmesh_stream, texture_dict["texture_type"])
                if TextureType(texture_dict["texture_type"]) is not TextureType.none:
                    write_string(rmesh_stream, texture_dict["texture_name"])

        write_integer(rmesh_stream, len(mesh_dict["vertices"]))
        for vertex_dict in mesh_dict["vertices"]:
            write_vector(rmesh_stream, vertex_dict["position"])
            if not is_coll:
                write_uv(rmesh_stream, vertex_dict["uv_render"])
                write_uv(rmesh_stream, vertex_dict["uv_lightmap"])
                write_color(rmesh_stream, vertex_dict["color"])
                if file_type == ExportFileType.rmesh_uer2:
                    write_vector(rmesh_stream, vertex_dict["normal"])

        write_integer(rmesh_stream, len(mesh_dict["triangles"]))
        for triangle_dict in mesh_dict["triangles"]:
            write_integer(rmesh_stream, triangle_dict["a"])
            write_integer(rmesh_stream, triangle_dict["b"])
            write_integer(rmesh_stream, triangle_dict["c"])

def write_rmesh(rmesh_dict, output_path, file_type):
    with output_path.open("wb") as rmesh_stream:
        if rmesh_dict["rmesh_file_type"] != "RoomMesh" and rmesh_dict["rmesh_file_type"] != "RoomMesh.HasTriggerBox" and rmesh_dict["rmesh_file_type"] != "RoomMesh2" and rmesh_dict["rmesh_file_type"] != "RM":
            raise ValueError('Input file was "%s" instead of "RoomMesh", "RoomMesh.HasTriggerBox", "RoomMesh2", or RM and therefore is not an RMESH file' % rmesh_dict["rmesh_file_type"])

        write_string(rmesh_stream, rmesh_dict["rmesh_file_type"])
        if file_type == ExportFileType.rmesh_salvage:
            write_byte(rmesh_stream, rmesh_dict["rmesh_version"])

        write_mesh_data(rmesh_stream, file_type, rmesh_dict["meshes"])
        if file_type == ExportFileType.rmesh_salvage:
            write_mesh_data(rmesh_stream, file_type, rmesh_dict["render_meshes"])

        write_mesh_data(rmesh_stream, file_type, rmesh_dict["collision_meshes"], True)
        if file_type == ExportFileType.rmesh_tb or file_type == ExportFileType.rmesh_salvage:
            write_integer(rmesh_stream, len(rmesh_dict["trigger_boxes"]))
            for trigger_box_dict in rmesh_dict["trigger_boxes"]:
                write_mesh_data(rmesh_stream, file_type, trigger_box_dict["meshes"], True)
                write_string(rmesh_stream, trigger_box_dict["name"])

        write_integer(rmesh_stream, len(rmesh_dict["entities"]))
        for entity_dict in rmesh_dict["entities"]:
            write_string(rmesh_stream, entity_dict["entity_type"])
            if entity_dict["entity_type"] == "screen":
                write_vector(rmesh_stream, entity_dict["position"])
                write_string(rmesh_stream, entity_dict["texture_name"])

            elif entity_dict["entity_type"] == "save_screen":
                write_vector(rmesh_stream, entity_dict["position"])
                write_string(rmesh_stream, entity_dict["model_name"])
                write_vector(rmesh_stream, entity_dict["euler_rotation"])
                write_vector(rmesh_stream, entity_dict["scale"])
                write_string(rmesh_stream, entity_dict["texture_name"])

            elif entity_dict["entity_type"] == "waypoint":
                write_vector(rmesh_stream, entity_dict["position"])

            elif entity_dict["entity_type"] == "light":
                write_vector(rmesh_stream, entity_dict["position"])
                write_float(rmesh_stream, entity_dict["range"])
                write_string(rmesh_stream, entity_dict["color"])
                write_float(rmesh_stream, entity_dict["intensity"])
                if file_type == ExportFileType.rmesh_uer2:
                    write_byte(rmesh_stream, entity_dict["has_sprite"])
                    write_float(rmesh_stream, entity_dict["sprite_scale"])
                    write_byte(rmesh_stream, entity_dict["casts_shadows"])
                    write_float(rmesh_stream, entity_dict["scattering"])
                    for ff_element in entity_dict["ff_array"]:
                        write_integer(rmesh_stream, ff_element)


            elif entity_dict["entity_type"] == "light_fix":
                if file_type == ExportFileType.rmesh_uer2:
                    write_vector(rmesh_stream, entity_dict["position"])
                    write_float(rmesh_stream, entity_dict["range"])
                    write_string(rmesh_stream, entity_dict["color"])
                    write_float(rmesh_stream, entity_dict["intensity"])
                    write_byte(rmesh_stream, entity_dict["has_sprite"])
                    write_float(rmesh_stream, entity_dict["sprite_scale"])
                    write_byte(rmesh_stream, entity_dict["casts_shadows"])
                    write_float(rmesh_stream, entity_dict["scattering"])
                    for ff_element in entity_dict["ff_array"]:
                        write_integer(rmesh_stream, ff_element)
                else:
                    write_vector(rmesh_stream, entity_dict["position"])
                    write_string(rmesh_stream, entity_dict["color"])
                    write_float(rmesh_stream, entity_dict["intensity"])
                    write_float(rmesh_stream, entity_dict["range"])

            elif entity_dict["entity_type"] == "spotlight":
                write_vector(rmesh_stream, entity_dict["position"])
                write_float(rmesh_stream, entity_dict["range"])
                write_string(rmesh_stream, entity_dict["color"])
                write_float(rmesh_stream, entity_dict["intensity"])
                if file_type == ExportFileType.rmesh_uer2:
                    write_byte(rmesh_stream, entity_dict["has_sprite"])
                    write_float(rmesh_stream, entity_dict["sprite_scale"])
                    write_byte(rmesh_stream, entity_dict["casts_shadows"])
                    write_2d_vector(rmesh_stream, entity_dict["direction"])
                    write_float(rmesh_stream, entity_dict["outer_cone_angle"])
                    write_float(rmesh_stream, entity_dict["scattering"])
                    for ff_element in entity_dict["ff_array"]:
                        write_integer(rmesh_stream, ff_element)
                else:
                    write_string(rmesh_stream, entity_dict["euler_rotation"])
                    write_integer(rmesh_stream, entity_dict["inner_cone_angle"])
                    write_integer(rmesh_stream, entity_dict["outer_cone_angle"])

            elif entity_dict["entity_type"] == "soundemitter":
                write_vector(rmesh_stream, entity_dict["position"])
                write_integer(rmesh_stream, entity_dict["id"])
                write_float(rmesh_stream, entity_dict["range"])

            elif entity_dict["entity_type"] == "model":
                write_string(rmesh_stream, entity_dict["model_name"])
                if not file_type == ExportFileType.rmesh_uer:
                    write_vector(rmesh_stream, entity_dict["position"])
                    write_vector(rmesh_stream, entity_dict["euler_rotation"])
                    write_vector(rmesh_stream, entity_dict["scale"])

            elif entity_dict["entity_type"] == "mesh":
                write_vector(rmesh_stream, entity_dict["position"])
                write_string(rmesh_stream, entity_dict["model_name"])
                write_vector(rmesh_stream, entity_dict["euler_rotation"])
                write_vector(rmesh_stream, entity_dict["scale"])
                write_byte(rmesh_stream, entity_dict["has_collision"])
                write_integer(rmesh_stream, entity_dict["fx"])
                write_string(rmesh_stream, entity_dict["texture_name"])

            elif entity_dict["entity_type"] == "item":
                write_vector(rmesh_stream, entity_dict["position"])
                if file_type == ExportFileType.rmesh or file_type == ExportFileType.rmesh_tb:
                    write_string(rmesh_stream, entity_dict["item_name"])

                write_string(rmesh_stream, entity_dict["model_name"])
                write_byte(rmesh_stream, entity_dict["use_custom_rotation"])
                write_vector(rmesh_stream, entity_dict["euler_rotation"])
                write_float(rmesh_stream, entity_dict["state_1"])
                write_float(rmesh_stream, entity_dict["state_2"])
                write_float(rmesh_stream, entity_dict["spawn_chance"])

            elif entity_dict["entity_type"] == "door":
                write_vector(rmesh_stream, entity_dict["position"])
                write_integer(rmesh_stream, entity_dict["door_type"])
                if file_type == ExportFileType.rmesh_salvage and rmesh_dict["rmesh_version"] >= 1:
                    write_integer(rmesh_stream, entity_dict["door_identifier"])
                    
                write_integer(rmesh_stream, entity_dict["key_card_level"])
                write_string(rmesh_stream, entity_dict["keypad_code"])
                write_float(rmesh_stream, entity_dict["angle"])
                write_byte(rmesh_stream, entity_dict["start_open"])
                if file_type == ExportFileType.rmesh_salvage:
                    write_byte(rmesh_stream, entity_dict["locked"])
                    write_byte(rmesh_stream, entity_dict["delete_half"])
                    write_byte(rmesh_stream, entity_dict["allow_scp_079_remote_control"])
                    write_vector(rmesh_stream, entity_dict["button_1_position"])
                    write_vector(rmesh_stream, entity_dict["button_1_angle"])
                    write_vector(rmesh_stream, entity_dict["button_2_position"])
                    write_vector(rmesh_stream, entity_dict["button_2_angle"])

                else:
                    write_byte(rmesh_stream, entity_dict["allow_scp_079_remote_control"])

            else:
                print("Unknown entity type: %s" % entity_dict["entity_type"])

        if file_type == ExportFileType.rmesh or file_type == ExportFileType.rmesh_tb:
            write_string(rmesh_stream, "EOF")
