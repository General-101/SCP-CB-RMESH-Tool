import os
from pathlib import Path
from enum import Enum, auto, Flag

from .common_functions import (read_null_string,
                               write_null_string,
                               read_integer,
                               write_integer,
                               read_short,
                               write_short,
                               read_byte,
                               write_byte,
                               read_float,
                               write_float,
                               read_vector,
                               write_vector)

class TerrainFlags(Flag):
    has_lightmap = auto()

class MeshFlags(Flag):
    exclude_scale = auto()
    unk1 = auto()
    unk2 = auto()
    unk3 = auto()
    has_vertex_colors = auto()

class MaterialFlags(Flag):
    unk0 = auto()
    has_extension = auto()
    unk1 = auto()
    unk2 = auto()

def read_3dw(file_path):
    _3dw_dict = {
        "map_version": 0,
        "map_flags": 0,
        "names": [],
        "materials": [],
        "mesh_references": {},
        "groups": {},
        "visgroups": {},
        "objects": [],
        "terrain": []
    }

    with file_path.open("rb") as _3dw_stream:
        _3dw_dict["map_version"] = read_short(_3dw_stream)
        _3dw_dict["map_flags"] = read_byte(_3dw_stream)

        name_count = read_integer(_3dw_stream)
        name_offset = read_integer(_3dw_stream)

        object_count = read_integer(_3dw_stream)
        object_offset = read_integer(_3dw_stream)

        _3dw_stream.seek(name_offset)
        for name_idx in range(name_count):
            _3dw_dict["names"].append(read_null_string(_3dw_stream))

        _3dw_stream.seek(object_offset)
        for object_idx in range(object_count):
            index = read_integer(_3dw_stream) - 1
            size = read_integer(_3dw_stream)

            name = _3dw_dict["names"][index] if 0 <= index < len(_3dw_dict["names"]) else None

            if name == "group":
                flags = read_byte(_3dw_stream)
                group_index = read_integer(_3dw_stream)

                new_group = {"flags": flags, "group_index": group_index}

                _3dw_dict["groups"][object_idx] = new_group

            elif name == "visgroup":
                flags = read_byte(_3dw_stream)
                group_name = _3dw_dict["names"][read_integer(_3dw_stream) - 1]

                color_r = read_byte(_3dw_stream)
                color_g = read_byte(_3dw_stream)
                color_b = read_byte(_3dw_stream)

                new_group = {"name": group_name, "color": (color_r, color_g, color_b)}

                _3dw_dict["visgroups"][object_idx] = new_group

            elif name == "meshreference":
                flags = read_byte(_3dw_stream)

                group_name = _3dw_dict["names"][read_integer(_3dw_stream) - 1]
                object_name = _3dw_dict["names"][read_integer(_3dw_stream) - 1]

                limb_count = read_byte(_3dw_stream)
                new_group = {"flags": flags, "group_name": group_name, "object_name": object_name, "limb_count": limb_count}

                _3dw_dict["mesh_references"][object_idx] = new_group

            elif name == "material":
                flags = read_byte(_3dw_stream)
                group_name = _3dw_dict["names"][read_integer(_3dw_stream) - 1]
                object_name = _3dw_dict["names"][read_integer(_3dw_stream) - 1]

                extension_name = ""
                if MaterialFlags.has_extension in MaterialFlags(flags):
                    extension_name = _3dw_dict["names"][read_integer(_3dw_stream) - 1]

                new_group = {"flags": flags, "group_name": group_name, "object_name": object_name, "extension_name": extension_name}
                _3dw_dict["materials"].append(object_name)

            else:
                _3dw_stream.seek(size, 1)

        _3dw_stream.seek(object_offset)
        for i in range(object_count):
            index = read_integer(_3dw_stream) - 1
            size = read_integer(_3dw_stream)

            name = _3dw_dict["names"][index] if 0 <= index < len(_3dw_dict["names"]) else None
            if name == "mesh":
                entity = {
                    "classname": "model",
                    "name": "model",
                    "flags": 0,
                    "properties": {},
                    "group_index": -1,
                    "visgroup_index": -1,
                    "color": (0, 0, 0),
                    "mesh_reference_index": -1,
                    "origin": (0, 0, 0),
                    "limb_data": []
                }

                entity["flags"] = read_byte(_3dw_stream)
                mesh_flags = MeshFlags(entity["flags"])

                key_count = read_integer(_3dw_stream)
                for key_idx in range(key_count):
                    key_name = _3dw_dict["names"][read_integer(_3dw_stream) - 1]
                    key_value = _3dw_dict["names"][read_integer(_3dw_stream) - 1]

                    entity["properties"][key_name] = key_value

                entity["group_index"] = read_integer(_3dw_stream) - 1
                entity["visgroup_index"] = read_integer(_3dw_stream) - 1
#                if visgroup_index in _3dw_dict["visgroups_dict"]:
#                    entity["visgroups"].append(_3dw_dict["visgroups_dict"][visgroup_index])

                red = read_byte(_3dw_stream)
                green = read_byte(_3dw_stream)
                blue = read_byte(_3dw_stream)
                entity["color"] = (red, green, blue)

                mesh_reference_index = read_integer(_3dw_stream) - 1
                #if "file" not in entity["properties"]:
                #    ref = next(q for q in _3dw_dict["mesh_references"] if q[0] == mesh_ref_index)
                #    entity["properties"]["file"] = ref[1]

                x = read_float(_3dw_stream)
                z = read_float(_3dw_stream)
                y = read_float(_3dw_stream)
                entity["origin"] = (x, y, z)

                pitch = read_float(_3dw_stream)
                yaw = read_float(_3dw_stream)
                roll = read_float(_3dw_stream)
                entity["properties"]["angles"] = (pitch, yaw, roll)

                x_scale = 1.0
                y_scale = 1.0
                z_scale = 1.0
                if not MeshFlags.exclude_scale in mesh_flags:
                    x_scale = read_float(_3dw_stream)
                    y_scale = read_float(_3dw_stream)
                    z_scale = read_float(_3dw_stream)
                
                entity["properties"]["scale"] = (x_scale, y_scale, z_scale)

                mesh_dict = _3dw_dict["mesh_references"].get(mesh_reference_index)
                if mesh_dict is not None:
                    limb_count = mesh_dict['limb_count']
                    for limb_idx in range(limb_count):
                        limb_dict = {"material_index": -1, "vertex_colors": []}

                        limb_dict["material_index"] = read_integer(_3dw_stream)
                        if MeshFlags.has_vertex_colors in mesh_flags:
                            vertex_count = read_short(_3dw_stream)
                            for color_idx in range(vertex_count):
                                red = read_byte(_3dw_stream)
                                green = read_byte(_3dw_stream)
                                blue = read_byte(_3dw_stream)
                                limb_dict["vertex_colors"].append((red, green, blue))

                        entity["limb_data"].append(limb_dict)

                _3dw_dict["objects"].append(entity)

            elif name == "entity":
                entity = {
                    "classname": None,
                    "name": None,
                    "flags": 0,
                    "properties": {},
                    "origin": (x, y, z),
                    "group_index": -1,
                    "visgroup_index": -1,
                }

                entity["flags"] = read_byte(_3dw_stream)

                x = read_float(_3dw_stream)
                z = read_float(_3dw_stream)
                y = read_float(_3dw_stream)
                entity["origin"] = (x, y, z)

                key_count = read_integer(_3dw_stream)
                for key_idx in range(key_count):
                    key_name_index = read_integer(_3dw_stream) - 1
                    key_value_index = read_integer(_3dw_stream) - 1

                    key_name = _3dw_dict["names"][key_name_index]
                    key_value = _3dw_dict["names"][key_value_index]
                    if _3dw_dict["names"][key_name_index] == "classname":
                        entity["classname"] = key_name
                        entity["name"] = key_value
                    else:
                        entity["properties"][key_name] = key_value

                entity["group_index"] = read_integer(_3dw_stream) - 1
                entity["visgroup_index"] = read_integer(_3dw_stream) - 1

#                if visgroup_index in _3dw_dict["visgroups_dict"]:
#                    entity["visgroups"].append(_3dw_dict["visgroups_dict"][visgroup_index])

                _3dw_dict["objects"].append(entity)

            elif name == "brush":
                entity = {
                    "classname": "brush",
                    "name": "brush",
                    "flags": 0,
                    "properties": {},
                    "group_index": -1,
                    "visgroup_index": -1,
                    "color": (0, 0, 0),
                    "vertices": [],
                    "faces": []
                }

                entity["flags"] = read_byte(_3dw_stream)
                key_count = read_integer(_3dw_stream)
                for key_idx in range(key_count):
                    key_name = _3dw_dict["names"][read_integer(_3dw_stream) - 1]
                    key_value = _3dw_dict["names"][read_integer(_3dw_stream) - 1]

                    entity["properties"][key_name] = key_value

                entity["group_index"] = read_integer(_3dw_stream) - 1
                entity["visgroup_index"] = read_integer(_3dw_stream) - 1

                red = read_byte(_3dw_stream)
                green = read_byte(_3dw_stream)
                blue = read_byte(_3dw_stream)
                entity["color"] = (red, green, blue)

                vertex_count = read_byte(_3dw_stream)
                for vertex_idx in range(vertex_count):
                    x = read_float(_3dw_stream)
                    z = read_float(_3dw_stream)
                    y = read_float(_3dw_stream)

                    entity["vertices"].append((x, y, z))

                face_count = read_byte(_3dw_stream)
                for face_idx in range(face_count):
                    face = {
                        "flags": 0,
                        "plane": (0.0, 0.0, 0.0, 0.0),
                        "texture_position": (0.0, 0.0),
                        "texture_scale": (1.0, 1.0),
                        "texture_rotation": (0.0, 0.0),
                        "u_plane": (0.0, 0.0, 0.0, 0.0),
                        "v_plane": (0.0, 0.0, 0.0, 0.0),
                        "luxel": 0.0,
                        "smooth_group": 0,
                        "material_index": 0,
                        "lightmap_index": 0,
                        "face_indices": []
                    }

                    face["flags"] = read_byte(_3dw_stream)
                    face["plane"] = [read_float(_3dw_stream) for p in range(4)]

                    face["texture_position"] = (read_float(_3dw_stream), read_float(_3dw_stream))
                    face["texture_scale"] = (read_float(_3dw_stream), read_float(_3dw_stream))
                    face["texture_rotation"] = (read_float(_3dw_stream), read_float(_3dw_stream))

                    face["u_plane"] = [read_float(_3dw_stream) for p in range(4)]
                    face["v_plane"] = [read_float(_3dw_stream) for p in range(4)]

                    face["luxel"] = read_float(_3dw_stream)

                    face["smooth_group"] = read_integer(_3dw_stream)
                    face["material_index"] = read_integer(_3dw_stream) - 1
                    if (face["flags"] & 16) != 0:
                        face["lightmap_index"] = read_integer(_3dw_stream)

                    point_count = read_byte(_3dw_stream)
                    for point_idx in range(point_count):
                        vertex = {
                            "vertex_index": 0,
                            "diffuse_texcoord": (0.0, 0.0),
                            "lightmap_texcoord": (0.0, 0.0)
                        }

                        vertex["vertex_index"] = read_byte(_3dw_stream)
                        vertex["diffuse_texcoord"] = (read_float(_3dw_stream), read_float(_3dw_stream))
                        if (face["flags"] & 16) != 0:
                            vertex["lightmap_texcoord"] = (read_float(_3dw_stream), read_float(_3dw_stream))

                        face["face_indices"].append(vertex)

                    entity["faces"].append(face)

                _3dw_dict["objects"].append(entity)

            elif name == "terrain":
                # TODO
                print(name)
                print(_3dw_stream.tell())
                print(size)

                terrain_dict = {"flags": 0,
                                "position": (0, 0, 0),
                                "width": 0.0,
                                "height": 0.0,
                                "object_name": "",
                                "resolution": 0,
                                "sectors": 0,
                                "detail_level": 0,
                                "unk0": 0,
                                "unk1": 0,
                                "colors": [],
                                "z_positions": [],
                                "unk2": 0,
                                "unk3": 0
                                }

                terrain_dict["flags"] = read_byte(_3dw_stream)
                terrain_dict["position"] = read_vector(_3dw_stream)
                terrain_dict["width"] = read_float(_3dw_stream)
                terrain_dict["height"] = read_float(_3dw_stream)

                terrain_dict["object_name"] = _3dw_dict["names"][read_integer(_3dw_stream) - 1]

                terrain_dict["resolution"] = read_integer(_3dw_stream)
                terrain_dict["sectors"] = read_integer(_3dw_stream)
                terrain_dict["detail_level"] = read_integer(_3dw_stream)

                terrain_dict["lightmap_resolution"] = read_float(_3dw_stream)
                terrain_dict["layer_count"] = read_integer(_3dw_stream)


                if TerrainFlags.has_lightmap in TerrainFlags(terrain_dict["flags"]):
                    list_length = (terrain_dict["resolution"] * terrain_dict["resolution"])
                    print(list_length)
                    for z_idx in range(list_length):
                        r = read_byte(_3dw_stream)
                        g = read_byte(_3dw_stream)
                        b = read_byte(_3dw_stream)
                        terrain_dict["colors"].append((r, g ,b))

                list_length = (terrain_dict["resolution"] + 1) * (terrain_dict["resolution"] + 1)
                print(list_length)
                for z_idx in range(list_length):
                    z = read_float(_3dw_stream)
                    terrain_dict["z_positions"].append(z)

                terrain_dict["unk1"] = read_integer(_3dw_stream)
                terrain_dict["unk3"] = read_integer(_3dw_stream)

                _3dw_dict["terrain"].append(terrain_dict)

            elif name == "lightmap":
                # TODO
                print(name)
                print(_3dw_stream.tell())
                print(size)
                _3dw_stream.seek(size, 1)
            else:
                _3dw_stream.seek(size, 1)

    return _3dw_dict
