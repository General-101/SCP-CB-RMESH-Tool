import re
import os
import bpy
import struct
import colorsys
import configparser

from math import radians
from enum import Enum, auto
from mathutils import Matrix, Vector, Quaternion, Euler

SHADER_RESOURCES = os.path.join(os.path.dirname(os.path.realpath(__file__)), "shader_resources.blend")
SHADER_NODE_NAMES = ("rmesh_material", "b3d_material", "cb_material")

ROOMSCALE = 0.00625

class ObjectType(Enum):
    exclude = 0
    mesh = auto()
    render = auto()
    collision = auto()
    trigger_box = auto()
    entity_screen = auto()
    entity_waypoint = auto()
    entity_light = auto()
    entity_spotlight = auto()
    entity_sound_emitter = auto()
    entity_model = auto()
    entity_item = auto()
    entity_door = auto()

class MaterialType(Enum):
    full = 0
    simple = auto()

def linear_to_gamma(v):
    return pow(v, 1.0 / 2.2)

def gamma_to_linear(v):
    return pow(v, 2.2)

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

def is_string_empty(string):
    is_empty = False
    if not string == None and (len(string) == 0 or string.isspace()):
        is_empty = True

    return is_empty

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

def get_file(file_name, use_image_set=True, generate_image_node=True, directory_path=""):
    extension_set = ("bmp", "jpg", "jpeg", "png")
    if not use_image_set:
        extension_set = ("b3d", "x")

    file_asset = None
    file_path = None
    game_path = bpy.context.preferences.addons[__package__].preferences.game_path
    if directory_path.lower().startswith("mods"):
        parts = directory_path.split(os.sep)
        part_count = len(parts)
        if part_count >= 3 and parts[0].lower() == "mods":
            directory_path = ""
            inner_parts = parts[2:]
            inner_part_count = len(inner_parts)
            for part_idx, part in enumerate(inner_parts):
                directory_path += part
                if part_idx < inner_part_count - 1:
                    directory_path += os.sep

    asset_directory = os.path.join(game_path, directory_path)
    if not is_string_empty(asset_directory) and file_name is not None:
        if not is_string_empty(directory_path):
            file_check = os.path.join(asset_directory, file_name)
            if os.path.isfile(file_check):
                file_path = file_check

            else:
                for file in os.listdir(asset_directory):
                    absolute_file_path = os.path.join(asset_directory, file)
                    if os.path.isfile(absolute_file_path):
                        for extension in extension_set:
                            file_name_w_ext = os.path.basename(file_name).lower()
                            file_name_wo_ext = file_name_w_ext.rsplit(".", 1)[0]
                            if file_name_wo_ext == "scp-012_diffuse": # The SCP 12 model references a texture that doesn't exist so putting this hack here - Gen
                                file_name_wo_ext = "scp-012_0"

                            if file.lower() == "%s.%s" % (file_name_wo_ext, extension):
                                file_path = os.path.join(asset_directory, file)
                                break

        if file_path is None:
            for root, dirs, files in os.walk(game_path):
                for file in files:
                    for extension in extension_set:
                        file_name_w_ext = os.path.basename(file_name).lower()
                        file_name_wo_ext = file_name_w_ext.rsplit(".", 1)[0]
                        if file.lower() == "%s.%s" % (file_name_wo_ext, extension):
                            file_path = os.path.join(root, file)
                            break

    if use_image_set and generate_image_node:
        if file_path is not None and os.path.isfile(file_path):
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
    else:
        print("This scene contains out of bounds material indicies. Defaulting to material slot 0")
        if mat_count >= 1:
            mat_slot = ob.material_slots[0]
            if mat_slot.link == 'OBJECT':
                if mat_slot is not None:
                    mat_name = mat_slot.material.name
            else:
                if ob.data.materials[0] is not None:
                    mat_name = ob.data.materials[0].name

    return mat_name

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

    use_nodes = True
    if bpy.app.version <= (5,0,0):
        use_nodes = mat.use_nodes

    if not mat == None and use_nodes and not mat.node_tree == None:
        for node in mat.node_tree.nodes:
            if node.type == "OUTPUT_MATERIAL" and node.is_active_output:
                output_material_node = node
                break

    if output_material_node is None:
        output_material_node = mat.node_tree.nodes.new("ShaderNodeOutputMaterial")

    return output_material_node

def get_shader_node(tree, shader_resource, shader_name):
    if not bpy.data.node_groups.get(shader_name):
        with bpy.data.libraries.load(shader_resource) as (data_from, data_to):
            data_to.node_groups.append(data_from.node_groups[data_from.node_groups.index(shader_name)])

    shader_node = tree.nodes.new('ShaderNodeGroup')
    shader_node.node_tree = bpy.data.node_groups.get(shader_name)

    return shader_node

def generate_texture_mapping(node_tree, input_node, input_key="Vector"):
    mapping_node = node_tree.nodes.new("ShaderNodeMapping")
    uv_node = node_tree.nodes.new("ShaderNodeUVMap")

    x, y = input_node.location
    mapping_node.location = (-180.0 + x, 0.0 + y) 
    uv_node.location = (-360.0 + x, 0.0 + y)

    connect_inputs(node_tree, uv_node, "UV", mapping_node, "Vector")
    connect_inputs(node_tree, mapping_node, "Vector", input_node, input_key)

    return mapping_node, uv_node

def flip(v):
    return ((v[0],v[2],v[1]) if len(v)<4 else (v[0], v[1],v[3],v[2]))

def clean_string(text):
    cleaned = re.sub(r'[^A-Za-z0-9_]', '', text)
    if cleaned and cleaned[0].isdigit():
        cleaned = '_' + cleaned

    return cleaned

def read_string(input_stream, encoding="utf-8"):
    return input_stream.read(read_integer(input_stream)).decode(encoding)

def write_string(input_stream, value, encoding="utf-8"):
    string_length = len(value)
    write_integer(input_stream, string_length)
    input_stream.write(struct.pack('<%ss' % string_length, bytes(value, encoding)))

def read_null_string(input_stream, encoding="utf-8"):
    s = bytearray()
    while True:
        c = input_stream.read(1)
        if c == b"\x00":
            break
        s += c
    return s.decode(encoding)

def write_null_string(input_stream, value, encoding="utf-8"):
    string_length = len(value)
    write_integer(input_stream, string_length)
    input_stream.write(struct.pack('<%ssx' % string_length, bytes(value, encoding)))

def read_integer(input_stream):
    return struct.unpack('<I', input_stream.read(4))[0]

def write_integer(input_stream, value):
    input_stream.write(struct.pack('<I', value))

def read_short(input_stream):
    return struct.unpack('<H', input_stream.read(2))[0]

def write_short(input_stream, value):
    input_stream.write(struct.pack('<H', value))

def read_byte(input_stream):
    return struct.unpack('<B', input_stream.read(1))[0]

def write_byte(input_stream, value):
    input_stream.write(struct.pack('<B', value))

def read_float(input_stream):
    return struct.unpack('<f', input_stream.read(4))[0]

def write_float(input_stream, value):
    input_stream.write(struct.pack('<f', value))

def read_vector(input_stream):
    return struct.unpack('<3f', input_stream.read(12))

def write_vector(input_stream, value):
    input_stream.write(struct.pack('<3f', *value))

def read_2d_vector(input_stream):
    return struct.unpack('<2f', input_stream.read(8))

def write_2d_vector(input_stream, value):
    input_stream.write(struct.pack('<2f', *value))

def read_uv(input_stream):
    return struct.unpack('<2f', input_stream.read(8))

def write_uv(input_stream, value):
    input_stream.write(struct.pack('<2f', *value))

def read_color(input_stream):
    return struct.unpack('<3B', input_stream.read(3))

def write_color(input_stream, value):
    input_stream.write(struct.pack('<3B', *value))

def get_ingame_scale(game_path, filepath, use_game_rules):
    room_scale = bpy.context.preferences.addons[__package__].preferences.room_scale
    result = Matrix().to_4x4()
    if not use_game_rules:
        result *= room_scale
        return result

    # We are taking the room scale in the game itself and getting the inverse.
    # We use it on the scales used by the game to get something we can scale independently. - Gen 
    game_scale_inverse = 256 
    game_scale = (1 / game_scale_inverse)

    items_ini = None
    npcs_ini = None

    npcs_ini_path = os.path.join(game_path, r"Data\NPCs.ini")
    items_ini_path = os.path.join(game_path, r"Data\items.ini")
    if os.path.isfile(items_ini_path):
        items_ini = configparser.ConfigParser()
        items_ini.read(items_ini_path)

    if os.path.isfile(npcs_ini_path):
        npcs_ini = configparser.ConfigParser()
        npcs_ini.read(npcs_ini_path)

    file_name_l = os.path.basename(filepath).lower()
    directory_name_l = os.path.basename(os.path.dirname(filepath)).lower()
    filepath_l = "%s_%s" % (directory_name_l, file_name_l)
    if filepath_l == "gfx_173box.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "gfx_apache.b3d":
        scale_val = (0.6 * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "gfx_apacherotor.b3d":
        # The scale here is inherited from the apache through entity parenting in scripts. - Gen
        scale_val = (0.6 * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "gfx_apacherotor2.b3d":
        # The scale here is inherited from the apache through entity parenting in scripts. - Gen
        scale_val = (0.6 * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "gfx_doorhit.b3d":
        scale_val = 1
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "gfx_lightcone.b3d":
        scale_val = (0.01 * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "items_420.x":
        ini_value = 0.0005
        if items_ini is not None:
            ini_value = float(items_ini.get("scp420j", "scale", fallback=0.0005))

        scale_val = (ini_value * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "items_427.b3d":
        ini_value = 0.001
        if items_ini is not None:
            ini_value = float(items_ini.get("scp427", "scale", fallback=0.001))

        scale_val = (ini_value * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "items_513.x":
        ini_value = 0.1
        if items_ini is not None:
            ini_value = float(items_ini.get("scp513", "scale", fallback=0.1))

        scale_val = (ini_value * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "items_badge.x":
        ini_value = 0.0001
        if items_ini is not None:
            ini_value = float(items_ini.get("badge", "scale", fallback=0.0001))

        scale_val = (ini_value * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "items_bdc.b3d":
        ini_value = 1.6
        if items_ini is not None:
            ini_value = float(items_ini.get("bdc", "scale", fallback=1.6))

        scale_val = (ini_value * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "items_clipboard.b3d":
        ini_value = 0.003
        if items_ini is not None:
            ini_value = float(items_ini.get("clipboard", "scale", fallback=0.003))

        scale_val = (ini_value * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "items_cup.x":
        ini_value = 0.04
        if items_ini is not None:
            ini_value = float(items_ini.get("cup", "scale", fallback=0.04))

        scale_val = (ini_value * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "items_cupliquid.x":
        ini_value = 0.04
        if items_ini is not None:
            ini_value = float(items_ini.get("cup", "scale", fallback=0.04))

        scale_val = (ini_value * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "items_electronics.x":
        ini_value = 0.0011
        if items_ini is not None:
            ini_value = float(items_ini.get("electronics", "scale", fallback=0.0011))

        scale_val = (ini_value * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "items_eyedrops.b3d":
        ini_value = 0.0012
        if items_ini is not None:
            ini_value = float(items_ini.get("eyedrops", "scale", fallback=0.0012))

        scale_val = (ini_value * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "items_firstaid.x":
        ini_value = 0.05
        if items_ini is not None:
            ini_value = float(items_ini.get("firstaid", "scale", fallback=0.05))

        scale_val = (ini_value * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "items_gasmask.b3d":
        ini_value = 0.02
        if items_ini is not None:
            ini_value = float(items_ini.get("gasmask", "scale", fallback=0.02))

        scale_val = (ini_value * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "items_happy.b3d":
        # Model is the same as bcd so reusing the scale setting. - Gen
        ini_value = 1.6
        if items_ini is not None:
            ini_value = float(items_ini.get("bdc", "scale", fallback=1.6))

        scale_val = (ini_value * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "items_hazmat.b3d":
        ini_value = 0.013
        if items_ini is not None:
            ini_value = float(items_ini.get("hazmatsuit", "scale", fallback=0.013))

        scale_val = (ini_value * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "items_hgib_skull1.b3d":
        ini_value = 0.015
        if items_ini is not None:
            ini_value = float(items_ini.get("scp1123", "scale", fallback=0.015))

        scale_val = (ini_value * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "items_key.b3d":
        ini_value = 0.001
        if items_ini is not None:
            ini_value = float(items_ini.get("key", "scale", fallback=0.001))

        scale_val = (ini_value * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "items_keycard.x":
        ini_value = 0.0004
        if items_ini is not None:
            ini_value = float(items_ini.get("key1", "scale", fallback=0.0004))

        scale_val = (ini_value * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "items_metalpanel.x":
        ini_value = 0.00390625
        if items_ini is not None:
            ini_value = float(items_ini.get("scp148", "scale", fallback=0.00390625))

        scale_val = (ini_value * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "items_navigator.x":
        ini_value = 0.0008
        if items_ini is not None:
            ini_value = float(items_ini.get("snav", "scale", fallback=0.0008))

        scale_val = (ini_value * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "items_note.x":
        ini_value = 0.0025
        if items_ini is not None:
            ini_value = float(items_ini.get("note682", "scale", fallback=0.0025))

        scale_val = (ini_value * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "items_nvg.b3d":
        ini_value = 0.02
        if items_ini is not None:
            ini_value = float(items_ini.get("nvgoggles", "scale", fallback=0.02))

        scale_val = (ini_value * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "items_origami.b3d":
        ini_value = 0.003
        if items_ini is not None:
            ini_value = float(items_ini.get("origami", "scale", fallback=0.003))

        scale_val = (ini_value * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "items_paper.x":
        ini_value = 0.003
        if items_ini is not None:
            ini_value = float(items_ini.get("oldpaper", "scale", fallback=0.003))

        scale_val = (ini_value * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "items_pill.b3d":
        ini_value = 0.0001
        if items_ini is not None:
            ini_value = float(items_ini.get("pill", "scale", fallback=0.0001))

        scale_val = (ini_value * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "items_radio.x":
        scale_val = (1 * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "items_scp-1499.b3d":
        ini_value = 0.023
        if items_ini is not None:
            ini_value = float(items_ini.get("scp1499", "scale", fallback=0.023))

        scale_val = (ini_value * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "items_scp1025.b3d":
        ini_value = 0.1
        if items_ini is not None:
            ini_value = float(items_ini.get("scp1025", "scale", fallback=0.1))

        scale_val = (ini_value * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "items_scp148.x":
        ini_value = 0.00390625
        if items_ini is not None:
            ini_value = float(items_ini.get("scp148", "scale", fallback=0.00390625))

        scale_val = (ini_value * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "items_scp714.b3d":
        ini_value = 0.3
        if items_ini is not None:
            ini_value = float(items_ini.get("scp714", "scale", fallback=0.3))

        scale_val = (ini_value * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "items_severedhand.b3d":
        ini_value = 0.04
        if items_ini is not None:
            ini_value = float(items_ini.get("hand", "scale", fallback=0.04))

        scale_val = (ini_value * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "items_vest.x":
        ini_value = 0.02
        if items_ini is not None:
            ini_value = float(items_ini.get("vest", "scale", fallback=0.02))

        scale_val = (ini_value * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "items_wallet.b3d":
        ini_value = 0.0005
        if items_ini is not None:
            ini_value = float(items_ini.get("wallet", "scale", fallback=0.0005))

        scale_val = (ini_value * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "battery_battery.x":
        ini_value = 0.008
        if items_ini is not None:
            ini_value = float(items_ini.get("bat", "scale", fallback=0.008))

        scale_val = (ini_value * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "syringe_syringe.b3d":
        ini_value = 0.005
        if items_ini is not None:
            ini_value = float(items_ini.get("syringe", "scale", fallback=0.005))

        scale_val = (ini_value * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "map_008_2.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_079.b3d":
        scale_val = (1.3 * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "map_1123_hb.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_173_2.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_294.x":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((game_scale_inverse, game_scale_inverse, game_scale_inverse)))
    elif filepath_l == "map_372_hb.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_914key.x":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_914knob.x":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_button.x":
        scale_val = (0.03 * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "map_buttoncode.x":
        scale_val = (0.03 * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "map_buttonkeycard.x":
        scale_val = (0.03 * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "map_buttonscanner.x":
        scale_val = (0.03 * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "map_cam.x":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_cambase.x":
        scale_val = (0.0015 * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "map_camhead.b3d":
        scale_val = (0.01 * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "map_camhead.x":
        scale_val = (0.01 * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "map_contdoorleft.x":
        scale_val = ((55 * (1 / game_scale_inverse)) * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "map_contdoorright.x":
        scale_val = ((55 * (1 / game_scale_inverse)) * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "map_door01.x":

        sx = ((204.0 * (1/256)) / (11.0814) * 256)
        sy = ((16.0 * (1/256)) / (1.05759) * 256)
        sz = ((312.0 * (1/256)) / (24.2875) * 256)

        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((sx, sy, sz)))
    elif filepath_l == "map_doorcoll.x":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_doorframe.x":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_elevatordoor.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_exit1terrain.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_fan.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_gateatunnel.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_gateawall1.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_gateawall2.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_gatea_hitbox1.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_heavydoor1.x":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_heavydoor2.x":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_introdesk.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_introdrawer.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_intro_labels.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_leverbase.x":
        scale_val = (0.04 * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "map_leverhandle.x":
        scale_val = (0.04 * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "map_lightgun.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_lightgunbase.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_medibay_props.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_monitor.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_monitor_checkpoint.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_pocketdimension2.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_pocketdimension3.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_pocketdimension4.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_pocketdimension5.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_pocketdimensionterrain.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_room012_2.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_room012_3.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_room049_hb.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_room1062.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_room2gw_pipes.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_room2tesla_caution.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_room3gw_pipes.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_room3offices_hb.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_room3storage_hb.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "map_room3z2_hb.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "dimension1499_1499object0_cull.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "dimension1499_1499object1.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "dimension1499_1499object10.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "dimension1499_1499object11.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "dimension1499_1499object12.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "dimension1499_1499object13.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "dimension1499_1499object14.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "dimension1499_1499object15.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "dimension1499_1499object2.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "dimension1499_1499object3.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "dimension1499_1499object4.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "dimension1499_1499object5.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "dimension1499_1499object6.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "dimension1499_1499object7.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "dimension1499_1499object8.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "dimension1499_1499object9.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "dimension1499_1499plane.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "forest_door.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "forest_door_frame.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "detail_rock.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "detail_treetest4.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "detail_treetest5.b3d":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "props_205.x":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "props_boxfile_a.x":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "props_boxfile_b.x":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "props_cabinet_a.x":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "props_cabinet_b.x":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "props_contdoorframe.x":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "props_crate1.x":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "props_crate2.x":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "props_crate3.x":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "props_elecbox.x":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "props_keyboard.x":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "props_lamp1.x":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "props_lamp2.x":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "props_lamp3.x":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "props_monitor.x":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "props_mug.x":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "props_officeseat_a.x":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "props_tank1.x":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "props_tank2.x":
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
    elif filepath_l == "npcs_035.b3d":
        # 35.6005 is the X dimension of the 035 model at 1.0 roomscale. - Gen
        scale_val = (0.5 / (room_scale * 35.6005)) * game_scale_inverse
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "npcs_035tentacle.b3d":
        scale_val = (0.065 * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "npcs_106_2.b3d":
        ini_value = 0.25
        if items_ini is not None:
            ini_value = float(npcs_ini.get("SCP-106", "scale", fallback=0.25))

        scale_val = ((ini_value / 2.2) * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "npcs_1499-1.b3d":
        ini_value = 0.08
        if items_ini is not None:
            ini_value = float(npcs_ini.get("SCP-1499-1", "scale", fallback=0.08))

        scale_val = ((ini_value / 4.0) * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "npcs_173_2.b3d":
        # 6.708 is the Y dimension of the 173 model at 1.0 roomscale. - Gen
        ini_value = 0.35
        if items_ini is not None:
            ini_value = float(npcs_ini.get("SCP-173", "scale", fallback=0.35))

        scale_val = ((ini_value / (room_scale * 6.708)) * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "npcs_205_demon1.b3d":
        scale_val = (0.05 * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "npcs_205_demon2.b3d":
        scale_val = (0.05 * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "npcs_205_demon3.b3d":
        scale_val = (0.05 * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "npcs_205_woman.b3d":
        scale_val = (0.05 * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "npcs_372.b3d":
        # 4.43868 is the X dimension of the 372 model at 1.0 roomscale. - Gen
        scale_val = ((0.35 / (room_scale * 4.43868)) * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "npcs_682arm.b3d":
        scale_val = (0.15 * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "npcs_bll.b3d":
        # 24.8496 is the X dimension of the bll model at 1.0 roomscale. - Gen
        scale_val = ((1.8 / (room_scale * 24.8496)) * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "npcs_classd.b3d":
        # 35.6005 is the X dimension of the D class model at 1.0 roomscale. - Gen
        scale_val = (0.5 / (room_scale * 35.6005))
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "npcs_clerk.b3d":
        # 33.5748 is the X dimension of the clerk model at 1.0 roomscale. - Gen
        scale_val = (0.5 / (room_scale * 33.5748))
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "npcs_duck_low_res.b3d":
        scale_val = (0.07 * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "npcs_forestmonster.b3d":
        ini_value = 0.5
        if items_ini is not None:
            ini_value = float(npcs_ini.get("Forestmonster", "scale", fallback=0.5))

        scale_val = ((ini_value / 20.0) * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "npcs_guard.b3d":
        ini_value = 0.29
        if items_ini is not None:
            ini_value = float(npcs_ini.get("Guard", "scale", fallback=0.29))

        scale_val = ((ini_value / 2.5) * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "npcs_mtf2.b3d":
        ini_value = 0.29
        if items_ini is not None:
            ini_value = float(npcs_ini.get("MTF", "scale", fallback=0.29))

        scale_val = ((ini_value / 2.5) * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "npcs_naziofficer.b3d":
        # 33.5956 is the X dimension of the naziofficer model at 1.0 roomscale. - Gen
        scale_val = ((1.8 / (room_scale * 33.5956)) * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "npcs_partyhat.b3d":
        # This model gets attached to 173 so we are reusing the scale from that. - Gen
        ini_value = 0.35
        if items_ini is not None:
            ini_value = float(npcs_ini.get("SCP-173", "scale", fallback=0.35))

        scale_val = ((ini_value / (room_scale * 6.708)) * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "npcs_s2.b3d":
        scale_val = (0.32 / 21.3) * game_scale_inverse
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "npcs_scp-049.b3d":
        ini_value = 1.2
        if items_ini is not None:
            ini_value = float(npcs_ini.get("SCP-049", "scale", fallback=1.2))

        scale_val = (ini_value * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "npcs_scp-066.b3d":
        ini_value = 0.17
        if items_ini is not None:
            ini_value = float(npcs_ini.get("SCP-066", "scale", fallback=0.17))

        scale_val = ((ini_value / 2.5) * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "npcs_scp-1048.b3d":
        scale_val = (0.05 * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "npcs_scp-1048a.b3d":
        scale_val = (0.05 * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "npcs_scp-1048pp.b3d":
        scale_val = (0.05 * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "npcs_scp-939.b3d":
        ini_value = 0.5
        if items_ini is not None:
            ini_value = float(npcs_ini.get("SCP-939", "scale", fallback=0.5))

        scale_val = ((ini_value / 2.5) * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "npcs_scp-966.b3d":
        ini_value = 0.5
        if items_ini is not None:
            ini_value = float(npcs_ini.get("SCP-966", "scale", fallback=0.5))

        scale_val = ((ini_value / 40.0) * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "npcs_scp096.b3d":
        ini_value = 0.6
        if items_ini is not None:
            ini_value = float(npcs_ini.get("SCP-096", "scale", fallback=0.6))

        scale_val = ((ini_value / 3.0) * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "npcs_zombie1.b3d":
        ini_value = 0.27
        if items_ini is not None:
            ini_value = float(npcs_ini.get("SCP-049-2", "scale", fallback=0.27))

        scale_val = ((ini_value / 2.5) * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))
    elif filepath_l == "npcs_zombiesurgeon.b3d":
        # 36.6699 is the X dimension of the zombiesurgeon model at 1.0 roomscale. - Gen
        scale_val = ((0.5 / (room_scale * 36.6699)) * game_scale_inverse)
        result = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((scale_val, scale_val, scale_val)))

    result *= room_scale

    return result
