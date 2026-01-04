import os
import json
import struct

from enum import Flag, Enum, auto

class TextureType(Enum):
    none = 0
    opaque = auto()
    lightmap = auto()
    transparent = auto()

def read_string(rmesh_stream):
    return rmesh_stream.read(read_unsigned_int(rmesh_stream)).decode('utf-8')

def write_string(rmesh_stream, value):
    string_length = len(value)
    write_unsigned_int(rmesh_stream, string_length)
    rmesh_stream.write(struct.pack('<%ss' % string_length, bytes(value, 'utf-8')))

def read_unsigned_int(rmesh_stream):
    return struct.unpack('<I', rmesh_stream.read(4))[0]

def write_unsigned_int(rmesh_stream, value):
    rmesh_stream.write(struct.pack('<I', value))

def read_byte(rmesh_stream):
    return struct.unpack('<B', rmesh_stream.read(1))[0]

def write_byte(rmesh_stream, value):
    rmesh_stream.write(struct.pack('<B', value))

def read_float(rmesh_stream):
    return struct.unpack('<f', rmesh_stream.read(4))[0]

def write_float(rmesh_stream, value):
    rmesh_stream.write(struct.pack('<f', value))

def read_vector(rmesh_stream):
    return struct.unpack('<3f', rmesh_stream.read(12))

def write_vector(rmesh_stream, value):
    rmesh_stream.write(struct.pack('<3f', *value))

def read_2d_vector(rmesh_stream):
    return struct.unpack('<2f', rmesh_stream.read(8))

def write_2d_vector(rmesh_stream, value):
    rmesh_stream.write(struct.pack('<2f', *value))

def read_uv(rmesh_stream):
    return struct.unpack('<2f', rmesh_stream.read(8))

def write_uv(rmesh_stream, value):
    rmesh_stream.write(struct.pack('<2f', *value))

def read_color(rmesh_stream):
    return struct.unpack('<3B', rmesh_stream.read(3))

def write_color(rmesh_stream, value):
    rmesh_stream.write(struct.pack('<3B', *value))

def read_rmesh(file_path):
    rmesh_dict = {
        "rmesh_file_type": "",
        "meshes": [],
        "collision_meshes": [],
        "entities": []
    }
    with open(file_path, "rb") as rmesh_stream:
        rmesh_dict["rmesh_file_type"] = read_string(rmesh_stream)
        if rmesh_dict["rmesh_file_type"] != "RoomMesh" and rmesh_dict["rmesh_file_type"] != "RoomMesh2":
            raise ValueError('Input file was "%s" instead of "RoomMesh or RoomMesh2 and therefore is not an RMESH file' % rmesh_dict["rmesh_file_type"])

        is_rmesh2 = False
        if rmesh_dict["rmesh_file_type"] == "RoomMesh2":
            is_rmesh2 = True

        mesh_count = read_unsigned_int(rmesh_stream)
        for mesh_idx in range(mesh_count):
            mesh_dict = {
                "textures": [],
                "vertices": [],
                "triangles": []
            }

            for texture_idx in range(2):
                texture_dict = {}

                texture_dict["texture_type"] = read_byte(rmesh_stream)
                texture_dict["texture_name"] = ""
                if TextureType(texture_dict["texture_type"]) is not TextureType.none:
                    texture_dict["texture_name"] = read_string(rmesh_stream)

                mesh_dict["textures"].append(texture_dict)

            vertex_count = read_unsigned_int(rmesh_stream)
            for vertex_idx in range(vertex_count):
                vertex_dict = {}

                vertex_dict["position"] = read_vector(rmesh_stream)
                vertex_dict["uv_render"] = read_uv(rmesh_stream)
                vertex_dict["uv_lightmap"] = read_uv(rmesh_stream)
                vertex_dict["color"] = read_color(rmesh_stream)
                if is_rmesh2:
                    vertex_dict["normal"] = read_vector(rmesh_stream)
                    print(vertex_dict["position"])
                    print(vertex_dict["normal"])
                    print()

                mesh_dict["vertices"].append(vertex_dict)

            triangle_count = read_unsigned_int(rmesh_stream)
            for triangle_idx in range(triangle_count):
                triangle_dict = {}

                triangle_dict["a"] = read_unsigned_int(rmesh_stream)
                triangle_dict["b"] = read_unsigned_int(rmesh_stream)
                triangle_dict["c"] = read_unsigned_int(rmesh_stream)

                mesh_dict["triangles"].append(triangle_dict)

            rmesh_dict["meshes"].append(mesh_dict)

        collision_count = read_unsigned_int(rmesh_stream)
        for collision_idx in range(collision_count):
            mesh_dict = {
                "vertices": [],
                "triangles": []
            }

            vertex_count = read_unsigned_int(rmesh_stream)
            for vertex_idx in range(vertex_count):
                vertex_dict = {}

                vertex_dict["position"] = read_vector(rmesh_stream)

                mesh_dict["vertices"].append(vertex_dict)

            triangle_count = read_unsigned_int(rmesh_stream)
            for triangle_idx in range(triangle_count):
                triangle_dict = {}

                triangle_dict["a"] = read_unsigned_int(rmesh_stream)
                triangle_dict["b"] = read_unsigned_int(rmesh_stream)
                triangle_dict["c"] = read_unsigned_int(rmesh_stream)

                mesh_dict["triangles"].append(triangle_dict)

            rmesh_dict["collision_meshes"].append(mesh_dict)

        entity_count = read_unsigned_int(rmesh_stream)
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
                if is_rmesh2:
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
                        ff_element = read_unsigned_int(rmesh_stream)
                        entity_dict["ff_array"].append(ff_element)
                else:
                    entity_dict["position"] = read_vector(rmesh_stream)
                    entity_dict["range"] = read_float(rmesh_stream)
                    entity_dict["color"] = read_string(rmesh_stream)
                    entity_dict["intensity"] = read_float(rmesh_stream)

            elif entity_dict["entity_type"] == "light_fix":
                if is_rmesh2:
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
                        ff_element = read_unsigned_int(rmesh_stream)
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
                if is_rmesh2:
                    entity_dict["has_sprite"] = read_byte(rmesh_stream)
                    entity_dict["sprite_scale"] = read_float(rmesh_stream)
                    entity_dict["casts_shadows"] = read_byte(rmesh_stream)
                    entity_dict["direction"] = read_2d_vector(rmesh_stream)
                    entity_dict["inner_cosine"] = read_float(rmesh_stream)
                    entity_dict["scattering"] = read_float(rmesh_stream)
                    entity_dict["ff_array"] = []
                    for ff in range(31):
                        ff_element = read_unsigned_int(rmesh_stream)
                        entity_dict["ff_array"].append(ff_element)
                else:
                    entity_dict["euler_rotation"] = read_string(rmesh_stream)
                    entity_dict["inner_cone_angle"] = read_unsigned_int(rmesh_stream)
                    entity_dict["outer_cone_angle"] = read_unsigned_int(rmesh_stream)

            elif entity_dict["entity_type"] == "soundemitter":
                entity_dict["position"] = read_vector(rmesh_stream)
                entity_dict["id"] = read_unsigned_int(rmesh_stream)
                entity_dict["range"] = read_float(rmesh_stream)

            elif entity_dict["entity_type"] == "model":
                entity_dict["model_name"] = read_string(rmesh_stream)
                if is_rmesh2:
                    vertex_dict["position"] = read_vector(rmesh_stream)
                    entity_dict["euler_rotation"] = read_vector(rmesh_stream)
                    entity_dict["scale"] = read_vector(rmesh_stream)

            elif entity_dict["entity_type"] == "mesh":
                entity_dict["position"] = read_vector(rmesh_stream)
                entity_dict["model_name"] = read_string(rmesh_stream)
                entity_dict["euler_rotation"] = read_vector(rmesh_stream)
                entity_dict["scale"] = read_vector(rmesh_stream)
                entity_dict["has_collision"] = read_byte(rmesh_stream)
                entity_dict["fx"] = read_unsigned_int(rmesh_stream)
                entity_dict["texture_name"] = read_string(rmesh_stream)
            else:
                print("Unknown entity type: %s" % entity_dict["entity_type"])

            rmesh_dict["entities"].append(entity_dict)

    return rmesh_dict

def write_rmesh(rmesh_dict, output_path):
    with open(output_path, "wb") as rmesh_stream:
        if rmesh_dict["rmesh_file_type"] != "RoomMesh" and rmesh_dict["rmesh_file_type"] != "RoomMesh2":
            raise ValueError("Input is not an RMESH file")

        is_rmesh2 = False
        if rmesh_dict["rmesh_file_type"] == "RoomMesh2":
            is_rmesh2 = True

        write_string(rmesh_stream, rmesh_dict["rmesh_file_type"])
        write_unsigned_int(rmesh_stream, len(rmesh_dict["meshes"]))
        for mesh_dict in rmesh_dict["meshes"]:
            for texture_dict in mesh_dict["textures"]:
                write_byte(rmesh_stream, texture_dict["texture_type"])
                if TextureType(texture_dict["texture_type"]) is not TextureType.none:
                    write_string(rmesh_stream, texture_dict["texture_name"])

            write_unsigned_int(rmesh_stream, len(mesh_dict["vertices"]))
            for vertex_dict in mesh_dict["vertices"]:
                write_vector(rmesh_stream, vertex_dict["position"])
                write_uv(rmesh_stream, vertex_dict["uv_render"])
                write_uv(rmesh_stream, vertex_dict["uv_lightmap"])
                write_color(rmesh_stream, vertex_dict["color"])
                if is_rmesh2:
                    write_vector(rmesh_stream, vertex_dict["normal"])

            write_unsigned_int(rmesh_stream, len(mesh_dict["triangles"]))
            for triangle_dict in mesh_dict["triangles"]:
                write_unsigned_int(rmesh_stream, triangle_dict["a"])
                write_unsigned_int(rmesh_stream, triangle_dict["b"])
                write_unsigned_int(rmesh_stream, triangle_dict["c"])

        write_unsigned_int(rmesh_stream, len(rmesh_dict["collision_meshes"]))
        for collision_dict in rmesh_dict["collision_meshes"]:
            write_unsigned_int(rmesh_stream, len(collision_dict["vertices"]))
            for vertex_dict in collision_dict["vertices"]:
                write_vector(rmesh_stream, vertex_dict["position"])

            write_unsigned_int(rmesh_stream, len(collision_dict["triangles"]))
            for triangle_dict in collision_dict["triangles"]:
                write_unsigned_int(rmesh_stream, triangle_dict["a"])
                write_unsigned_int(rmesh_stream, triangle_dict["b"])
                write_unsigned_int(rmesh_stream, triangle_dict["c"])

        write_unsigned_int(rmesh_stream, len(rmesh_dict["entities"]))
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
                if is_rmesh2:
                    write_vector(rmesh_stream, entity_dict["position"])
                    write_float(rmesh_stream, entity_dict["range"])
                    write_string(rmesh_stream, entity_dict["color"])
                    write_float(rmesh_stream, entity_dict["intensity"])
                    write_byte(rmesh_stream, entity_dict["has_sprite"])
                    write_float(rmesh_stream, entity_dict["sprite_scale"])
                    write_byte(rmesh_stream, entity_dict["casts_shadows"])
                    write_float(rmesh_stream, entity_dict["scattering"])
                    for ff_element in entity_dict["ff_array"]:
                        write_unsigned_int(rmesh_stream, ff_element)
                else:
                    write_vector(rmesh_stream, entity_dict["position"])
                    write_float(rmesh_stream, entity_dict["range"])
                    write_string(rmesh_stream, entity_dict["color"])
                    write_float(rmesh_stream, entity_dict["intensity"])

            elif entity_dict["entity_type"] == "light_fix":
                if is_rmesh2:
                    write_vector(rmesh_stream, entity_dict["position"])
                    write_float(rmesh_stream, entity_dict["range"])
                    write_string(rmesh_stream, entity_dict["color"])
                    write_float(rmesh_stream, entity_dict["intensity"])
                    write_byte(rmesh_stream, entity_dict["has_sprite"])
                    write_float(rmesh_stream, entity_dict["sprite_scale"])
                    write_byte(rmesh_stream, entity_dict["casts_shadows"])
                    write_float(rmesh_stream, entity_dict["scattering"])
                    for ff_element in entity_dict["ff_array"]:
                        write_unsigned_int(rmesh_stream, ff_element)
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
                if is_rmesh2:
                    write_byte(rmesh_stream, entity_dict["has_sprite"])
                    write_float(rmesh_stream, entity_dict["sprite_scale"])
                    write_byte(rmesh_stream, entity_dict["casts_shadows"])
                    write_2d_vector(rmesh_stream, entity_dict["direction"])
                    write_float(rmesh_stream, entity_dict["inner_cosine"])
                    write_float(rmesh_stream, entity_dict["scattering"])
                    for ff_element in entity_dict["ff_array"]:
                        write_unsigned_int(rmesh_stream, ff_element)
                else:
                    write_string(rmesh_stream, entity_dict["euler_rotation"])
                    write_unsigned_int(rmesh_stream, entity_dict["inner_cone_angle"])
                    write_unsigned_int(rmesh_stream, entity_dict["outer_cone_angle"])

            elif entity_dict["entity_type"] == "soundemitter":
                write_vector(rmesh_stream, entity_dict["position"])
                write_unsigned_int(rmesh_stream, entity_dict["id"])
                write_float(rmesh_stream, entity_dict["range"])

            elif entity_dict["entity_type"] == "model":
                write_string(rmesh_stream, entity_dict["model_name"])
                if is_rmesh2:
                    write_vector(rmesh_stream, entity_dict["position"])
                    write_vector(rmesh_stream, entity_dict["euler_rotation"])
                    write_vector(rmesh_stream, entity_dict["scale"])

            elif entity_dict["entity_type"] == "mesh":
                write_vector(rmesh_stream, entity_dict["position"])
                write_string(rmesh_stream, entity_dict["model_name"])
                write_vector(rmesh_stream, entity_dict["euler_rotation"])
                write_vector(rmesh_stream, entity_dict["scale"])
                write_byte(rmesh_stream, entity_dict["has_collision"])
                write_unsigned_int(rmesh_stream, entity_dict["fx"])
                write_string(rmesh_stream, entity_dict["texture_name"])
