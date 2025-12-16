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
        has_room_template = True
        rmesh_dict["rmesh_file_type"] = read_string(rmesh_stream)
        if rmesh_dict["rmesh_file_type"] != "RoomMesh":
            raise ValueError("Input is not an RMESH file")

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
                texture_dict["texture_name"] = None
                if TextureType(texture_dict["texture_type"]) is not TextureType.none:
                    texture_dict["texture_name"] = read_string(rmesh_stream)

                mesh_dict["textures"].append(texture_dict)

            vertex_count = read_unsigned_int(rmesh_stream)
            for vertex_idx in range(vertex_count):
                vertex_dict = {}

                vertex_dict["position"] = read_vector(rmesh_stream)
                vertex_dict["uv1"] = read_uv(rmesh_stream)
                vertex_dict["uv2"] = read_uv(rmesh_stream)
                vertex_dict["color"] = read_color(rmesh_stream)

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
        if has_room_template: # original this was the arg rt in the original function. Need to find out if this is just a given. - Gen
            for entity_idx in range(entity_count):
                entity_dict = {}
                entity_dict["entity_type"] = read_string(rmesh_stream)
                if entity_dict["entity_type"] == "screen":
                    entity_dict["position"] = read_vector(rmesh_stream) # Not sure if this is actually a position but it's 3 floats. - Gen
                    entity_dict["texture_name"] = read_string(rmesh_stream)

                elif entity_dict["entity_type"] == "save_screen":
                    entity_dict["position"] = read_vector(rmesh_stream)
                    entity_dict["texture_name"] = read_string(rmesh_stream)
                    entity_dict["euler_rotation"] = read_vector(rmesh_stream)
                    entity_dict["scale"] = read_vector(rmesh_stream)
                    entity_dict["image_path"] = read_string(rmesh_stream)

                elif entity_dict["entity_type"] == "waypoint":
                    entity_dict["position"] = read_vector(rmesh_stream)

                elif entity_dict["entity_type"] == "light":
                    entity_dict["position"] = read_vector(rmesh_stream)
                    entity_dict["radius"] = read_float(rmesh_stream)
                    entity_dict["light_color"] = read_string(rmesh_stream)
                    entity_dict["intensity"] = read_float(rmesh_stream)

                elif entity_dict["entity_type"] == "light_fix":
                    entity_dict["position"] = read_vector(rmesh_stream)
                    entity_dict["light_color"] = read_string(rmesh_stream)
                    entity_dict["intensity"] = read_float(rmesh_stream)
                    entity_dict["radius"] = read_float(rmesh_stream)

                elif entity_dict["entity_type"] == "spotlight":
                    entity_dict["position"] = read_vector(rmesh_stream)
                    entity_dict["radius"] = read_float(rmesh_stream)
                    entity_dict["light_color"] = read_string(rmesh_stream)
                    entity_dict["intensity"] = read_float(rmesh_stream)
                    entity_dict["angles"] = read_string(rmesh_stream)
                    entity_dict["inner_cone_angle"] = read_unsigned_int(rmesh_stream)
                    entity_dict["outer_cone_angle"] = read_unsigned_int(rmesh_stream)

                elif entity_dict["entity_type"] == "soundemitter":
                    entity_dict["position"] = read_vector(rmesh_stream)
                    entity_dict["id"] = read_unsigned_int(rmesh_stream)
                    entity_dict["radius"] = read_float(rmesh_stream)

                elif entity_dict["entity_type"] == "model":
                    entity_dict["model_name"] = read_string(rmesh_stream)

                elif entity_dict["entity_type"] == "mesh":
                    entity_dict["position"] = read_vector(rmesh_stream)
                    entity_dict["mesh_name"] = read_string(rmesh_stream)
                    entity_dict["euler_rotation"] = read_vector(rmesh_stream)
                    entity_dict["scale"] = read_vector(rmesh_stream)
                    entity_dict["has_collision"] = read_byte(rmesh_stream)
                    entity_dict["fx"] = read_unsigned_int(rmesh_stream)
                    entity_dict["texture_name"] = read_string(rmesh_stream)

                rmesh_dict["entities"].append(entity_dict)

    return rmesh_dict

def write_rmesh(rmesh_dict, output_path):
    with open(output_path, "wb") as rmesh_stream:
        has_room_template = True
        if rmesh_dict["rmesh_file_type"] != "RoomMesh":
            raise ValueError("Input is not an RMESH file")

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
                write_uv(rmesh_stream, vertex_dict["uv1"])
                write_uv(rmesh_stream, vertex_dict["uv2"])
                write_color(rmesh_stream, vertex_dict["color"])

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

file_path = "model.rmesh"
json_path = "dump.json"
output_path = "model.rmesh"

rmesh_dict = read_rmesh(file_path)
with open(json_path, 'w', encoding ='utf8') as json_file:
    json.dump(rmesh_dict, json_file, ensure_ascii = True, indent=4)

write_rmesh(rmesh_dict, output_path)
