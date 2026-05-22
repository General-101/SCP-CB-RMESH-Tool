import os
import bpy
import bmesh

from math import radians, ceil, log2, sqrt
from pathlib import Path
from enum import Enum, auto
from .process_rmesh import ImportFileType
from mathutils import Matrix, Vector, Euler
from .scene_x import import_scene as import_x
from .scene_b3d import import_scene as import_b3d
from .common_functions import ObjectType, get_output_material_node, get_linked_node, connect_inputs, SHADER_NODE_NAMES

# Notes
# Room scale seems to be 0.00390625
# The inverse of this is 256
# In order for the scale value to work in our Blender scene it seems we need to do whatever math the BB asks for and then multiply 256 against the result
# positions seem to be good when doing whatever the bb asks for and then multipling with 1.6 probably cause of the scale stuff we do
# I'm not sure where the other plugin got 0.00625 but the value I pulled from the game might be the real scale I need to set the imported assets to to match the ingame scale.

class DoorType(Enum):
    normal = 0
    big = auto()
    heavy = auto()
    elevator = auto()

class ButtonType(Enum):
    normal = 0
    code = auto()
    keycard = auto()
    scanner = auto()

class DoorState(Enum):
    closed = 0
    open = auto()

def create_object(ob_bm, ob_data, ob_transform, model_path):
    if str(model_path).lower().endswith(".x"):
        material_count = len(ob_data.materials)

        temp_data = bpy.data.meshes.new("door_entity")
        bm = bmesh.new()
        is_simple=True
        import_x(bpy.context, model_path, print, bm, ob_data, is_simple)
        for f in bm.faces:
            f.material_index = material_count + f.material_index

        bm.to_mesh(temp_data)
        temp_data.transform(ob_transform)
        ob_bm.from_mesh(temp_data)
        bm.free()
        bpy.data.meshes.remove(temp_data)

    if str(model_path).lower().endswith(".b3d"):
        material_count = len(ob_data.materials)

        temp_data = bpy.data.meshes.new("door_entity")
        bm = bmesh.new()
        is_simple=True
        import_b3d(bpy.context, model_path, False, True, print, bm, ob_data, is_simple)
        for f in bm.faces:
            f.material_index = material_count + f.material_index

        bm.to_mesh(temp_data)
        temp_data.transform(ob_transform)
        ob_bm.from_mesh(temp_data)
        bm.free()
        bpy.data.meshes.remove(temp_data)

def create_door(door_type=DoorType.normal, button_type=ButtonType.normal, door_state=DoorState.closed, door_halved=False, file_type=ImportFileType.rmesh, entity_idx=0, sd_ob=None, sba_ob=None, sbb_ob=None):
    if sd_ob:
        door_ob_data = sd_ob.data

    else:
        door_ob_data = bpy.data.meshes.new("door_entity")

    ob_bm = bmesh.new()

    game_path = bpy.context.preferences.addons[__package__].preferences.game_path
    room_scale = bpy.context.preferences.addons[__package__].preferences.room_scale
    BigDoorLeftPath = Path(os.path.join(game_path, r"GFX\map\ContDoorLeft.x"))
    BigDoorRightPath = Path(os.path.join(game_path, r"GFX\map\ContDoorRight.x"))
    HeavyDoorLeftPath = Path(os.path.join(game_path, r"GFX\map\heavydoor1.x"))
    HeavyDoorRightPath = Path(os.path.join(game_path, r"GFX\map\heavydoor2.x"))
    ElevatorDoorsPath = Path(os.path.join(game_path, r"GFX\map\elevatordoor.b3d"))
    DoorFramePath = Path(os.path.join(game_path, r"GFX\map\doorframe.x"))
    DoorPath = Path(os.path.join(game_path, r"GFX\map\door01.x"))
    ButtonPath = Path(os.path.join(game_path, r"GFX\map\Button.x"))
    if button_type == ButtonType.code:
        ButtonPath = Path(os.path.join(game_path, r"GFX\map\ButtonCode.x"))
    elif button_type == ButtonType.keycard:
        ButtonPath = Path(os.path.join(game_path, r"GFX\map\ButtonKeycard.x"))
    elif button_type == ButtonType.scanner:
        ButtonPath = Path(os.path.join(game_path, r"GFX\map\ButtonScanner.x"))

    if door_type == DoorType.big:
        x = 0
        if not door_state == DoorState.closed:
            x = 203.712 * room_scale

        if door_halved:
            ob_matrix = Matrix.LocRotScale(Vector((x, 0, 0)), Euler((0, 0, radians(180))), Vector((55, 55, 55)))
            create_object(ob_bm, door_ob_data, ob_matrix, BigDoorRightPath)
        else:
            ob_matrix = Matrix.LocRotScale(Vector((-x, 0, 0)), Euler((0, 0, radians(180))), Vector((55, 55, 55)))
            create_object(ob_bm, door_ob_data, ob_matrix, BigDoorLeftPath)
            ob_matrix = Matrix.LocRotScale(Vector((x, 0, 0)), Euler((0, 0, radians(180))), Vector((55, 55, 55)))
            create_object(ob_bm, door_ob_data, ob_matrix, BigDoorRightPath)

    elif door_type == DoorType.heavy:
        ax = 0
        bx = 0
        if not door_state == DoorState.closed:
            ax = 121.6 * room_scale
            bx = 171.84 * room_scale

        if door_halved:
            ob_matrix = Matrix.LocRotScale(Vector((bx, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
            create_object(ob_bm, door_ob_data, ob_matrix, HeavyDoorLeftPath)
        else:
            ob_matrix = Matrix.LocRotScale(Vector((-ax, 0, 0)), Euler((0, 0, radians(180))), Vector((1, 1, 1)))
            create_object(ob_bm, door_ob_data, ob_matrix, HeavyDoorRightPath)
            ob_matrix = Matrix.LocRotScale(Vector((bx, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
            create_object(ob_bm, door_ob_data, ob_matrix, HeavyDoorLeftPath)

        ob_matrix = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
        create_object(ob_bm, door_ob_data, ob_matrix, DoorFramePath)

    elif door_type == DoorType.elevator:
        x = 0
        if not door_state == DoorState.closed:
            x = 89.6 * room_scale

        ob_matrix = Matrix.LocRotScale(Vector((x, 0, 0)), Euler((radians(0), 0, radians(0))), Vector((1, 1, 1)))
        create_object(ob_bm, door_ob_data, ob_matrix, ElevatorDoorsPath)
        ob_matrix = Matrix.LocRotScale(Vector((-x, 0, 0)), Euler((radians(0), 0, radians(180))), Vector((1, 1, 1)))
        create_object(ob_bm, door_ob_data, ob_matrix, ElevatorDoorsPath)

        ob_matrix = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
        create_object(ob_bm, door_ob_data, ob_matrix, DoorFramePath)

    else:
        x = 0
        if not door_state == DoorState.closed:
            x = 184.448 * room_scale

        #Values on the right are hardcoded door01.x model dimensions at roomscale 1. Just easier than having a setup to calculate it from the model file.
        #Values on the left are from the bb game code. - Gen
        sx = (204.0 * room_scale) * (1 / (11.0814 * room_scale))
        sy = (16.0 * room_scale) * (1 /(1.05759 * room_scale))
        sz = (312.0 * room_scale) * (1 / (24.2875 * room_scale))

        if door_halved:
            ob_matrix = Matrix.LocRotScale(Vector((x, 0, 0)), Euler((0, 0, 0)), Vector((sx, sy, sz)))
            create_object(ob_bm, door_ob_data, ob_matrix, DoorPath)
        else:
            ob_matrix = Matrix.LocRotScale(Vector((-x, -8 * room_scale, 0)), Euler((0, 0, radians(180))), Vector((sx, sy, sz)))
            create_object(ob_bm, door_ob_data, ob_matrix, DoorPath)
            ob_matrix = Matrix.LocRotScale(Vector((x, 8 * room_scale, 0)), Euler((0, 0, 0)), Vector((sx, sy, sz)))
            create_object(ob_bm, door_ob_data, ob_matrix, DoorPath)

        ob_matrix = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
        create_object(ob_bm, door_ob_data, ob_matrix, DoorFramePath)

    ob_bm.to_mesh(door_ob_data)
    ob_bm.free()

    if sd_ob:
        door_ob = sd_ob

    else:
        door_ob = bpy.data.objects.new("%s door" % entity_idx, door_ob_data)

    if sba_ob:
        button_a_ob_data = sba_ob.data

    else:
        button_a_ob_data = bpy.data.meshes.new("button_a_entity")

    if sba_ob:
        button_b_ob_data = sbb_ob.data

    else:
        button_b_ob_data = bpy.data.meshes.new("button_b_entity")

    button_a_ob_bm = bmesh.new()
    button_b_ob_bm = bmesh.new()
    ob_bm = bmesh.new()
    button_scale = Vector((7.68, 7.68, 7.68))
    if door_type == DoorType.big:
        create_object(button_a_ob_bm, button_a_ob_data, Matrix(), ButtonPath)
        create_object(button_b_ob_bm, button_b_ob_data, Matrix(), ButtonPath)
        button_a_ob_bm.to_mesh(button_a_ob_data)
        button_a_ob_bm.free()
        button_b_ob_bm.to_mesh(button_b_ob_data)
        button_b_ob_bm.free()

        ob_a_matrix = Matrix.LocRotScale(room_scale * Vector((432, -192, 179.2)), Euler((0, 0, radians(-90))), button_scale)
        ob_b_matrix = Matrix.LocRotScale(room_scale * Vector((-432, 192, 179.2)), Euler((0, 0, radians(90))), button_scale)
        if sba_ob:
            button_a_ob = sba_ob

        else:
            button_a_ob = bpy.data.objects.new("%s door_button_a" % entity_idx, button_a_ob_data)
            button_a_ob.parent = door_ob
            button_a_ob.matrix_world = ob_a_matrix

        if sbb_ob:
            button_b_ob = sbb_ob

        else:
            button_b_ob = bpy.data.objects.new("%s door_button_b" % entity_idx, button_b_ob_data)
            button_b_ob.parent = door_ob
            button_b_ob.matrix_world = ob_b_matrix

    else:
        create_object(button_a_ob_bm, button_a_ob_data, Matrix(), ButtonPath)
        create_object(button_b_ob_bm, button_b_ob_data, Matrix(), ButtonPath)
        button_a_ob_bm.to_mesh(button_a_ob_data)
        button_a_ob_bm.free()
        button_b_ob_bm.to_mesh(button_b_ob_data)
        button_b_ob_bm.free()

        ob_a_matrix = Matrix.LocRotScale(room_scale * Vector((153.6, -25.6, 179.2)), Euler((0, 0, 0)), button_scale)
        ob_b_matrix = Matrix.LocRotScale(room_scale * Vector((-153.6, 25.6, 179.2)), Euler((0, 0, radians(180))), button_scale)

        if sba_ob:
            button_a_ob = sba_ob

        else:
            button_a_ob = bpy.data.objects.new("%s door_button_a" % entity_idx, button_a_ob_data)
            button_a_ob.parent = door_ob
            button_a_ob.matrix_world = ob_a_matrix

        if sbb_ob:
            button_b_ob = sbb_ob

        else:
            button_b_ob = bpy.data.objects.new("%s door_button_b" % entity_idx, button_b_ob_data)
            button_b_ob.parent = door_ob
            button_b_ob.matrix_world = ob_b_matrix

    return door_ob, button_a_ob, button_b_ob

def connect_lightmaps():
    for mat in bpy.data.materials:
        use_nodes = True
        if bpy.app.version <= (5,0,0):
            use_nodes = mat.use_nodes

        if not use_nodes or not mat.node_tree:
            continue

        nodes = mat.node_tree.nodes
        links = mat.node_tree.links

        output_node = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL'), None)
        if not output_node:
            continue

        surface_input = output_node.inputs.get("Surface")
        if not surface_input or not surface_input.is_linked:
            continue

        shader_node = surface_input.links[0].from_node
        if not (shader_node.type == 'GROUP' and shader_node.node_tree and shader_node.node_tree.name == "cb_material"):
            continue

        lightmap_input = shader_node.inputs.get("Light Map")
        if not lightmap_input:
            continue

        if lightmap_input.is_linked:
            continue

        alpha_input = shader_node.inputs.get("Diffuse Map Alpha")
        if not alpha_input:
            continue

        if alpha_input.is_linked:
            continue

        lm_node = None
        for node in nodes:
            if (node.type == 'TEX_IMAGE' and node.image and "lm" in node.image.name.lower()):
                lm_node = node
                break

        if not lm_node:
            continue

        color_output = lm_node.outputs.get("Color")
        if color_output:
            links.new(color_output, lightmap_input)

def disconnect_lightmaps():
    for mat in bpy.data.materials:
        use_nodes = True
        if bpy.app.version <= (5,0,0):
            use_nodes = mat.use_nodes

        if not use_nodes or not mat.node_tree:
            continue

        nodes = mat.node_tree.nodes
        links = mat.node_tree.links


        output_node = None
        for node in nodes:
            if node.type == 'OUTPUT_MATERIAL':
                output_node = node
                break

        if not output_node:
            continue

        surface_input = output_node.inputs.get("Surface")
        if not surface_input or not surface_input.is_linked:
            continue

        shader_node = surface_input.links[0].from_node
        if shader_node.type == 'GROUP' and shader_node.node_tree and shader_node.node_tree.name == "cb_material":
            lightmap_input = shader_node.inputs.get("Light Map")
            if not lightmap_input or not lightmap_input.is_linked:
                continue

            tex_image_node = None
            for link in lightmap_input.links:
                from_node = link.from_node
                if from_node.type == 'TEX_IMAGE':
                    tex_image_node = from_node

                links.remove(link)

            if tex_image_node:
                nodes.active = tex_image_node

MIN_RES = 32
MAX_RES = 4096
TEXEL_DENSITY = 128

def get_object_surface_area(obj, depsgraph):
    eval_obj = obj.evaluated_get(depsgraph)
    mesh = eval_obj.to_mesh()

    bm = bmesh.new()
    bm.from_mesh(mesh)

    scale = obj.matrix_world.to_scale()
    scale_factor = scale.x * scale.y * scale.z

    area = sum(f.calc_area() for f in bm.faces) * scale_factor

    bm.free()
    eval_obj.to_mesh_clear()

    return area

def next_power_of_two(x):
    return 2 ** ceil(log2(x))

def compute_lightmap_resolution(area):
    texels = area * (TEXEL_DENSITY ** 2)
    resolution = sqrt(texels)
    resolution = next_power_of_two(resolution)
    resolution = max(MIN_RES, min(MAX_RES, resolution))

    return int(resolution)

def run_bake(context, lightmap_ob, generate_vertex_colors=False, render_name="uvmap_render", lightmap_name="uvmap_lightmap"):
    lightmap_ob.select_set(True)
    context.view_layer.objects.active = lightmap_ob
    uv_layers = lightmap_ob.data.uv_layers
    if generate_vertex_colors:
        color_attribute = lightmap_ob.data.attributes.active_color
        if lightmap_ob.data.attributes.active_color == None:
            color_attribute = lightmap_ob.data.attributes.new(name="color", type="BYTE_COLOR", domain="POINT")
            lightmap_ob.data.attributes.active_color_name = "color"
            lightmap_ob.data.attributes.render_color_index = 0

        uv_layers[render_name].active_render = True
        uv_layers[render_name].active = True 
        target_name = 'VERTEX_COLORS'
        bake_layer = render_name
    else:
        uv_layers[render_name].active_render = True
        uv_layers[lightmap_name].active = True 
        target_name = 'IMAGE_TEXTURES'
        bake_layer = lightmap_name

    bpy.context.view_layer.update()
    context.scene.render.engine = 'CYCLES'
    
    bpy.ops.object.bake(
        type='DIFFUSE',
        pass_filter={'DIRECT','INDIRECT'}, 
        margin=context.scene.render.bake.margin,
        margin_type=context.scene.render.bake.margin_type, 
        use_clear=True,
        use_selected_to_active=False,
        target=target_name,
        uv_layer=bake_layer
    )
    
    lightmap_ob.select_set(False)
    context.view_layer.objects.active = None

def get_used_materials(mesh):
    used_materials = set()

    for poly in mesh.polygons:
        idx = poly.material_index
        if 0 <= idx < len(mesh.materials):
            mat = mesh.materials[idx]
            if mat:
                used_materials.add(mat)

    return used_materials

def bake_lightmaps(context):
    bpy.ops.wm.console_toggle()
    selected_obs = context.selected_objects
    depsgraph = context.evaluated_depsgraph_get()

    ob_groups = {}
    for ob in selected_obs:
        cb_type = ObjectType(int(ob.cb.object_type))
        uv_layer_count = len(ob.data.uv_layers)
        if ob.type == "MESH" and cb_type == ObjectType.mesh and uv_layer_count >= 2:
            mesh_name = ob.data.name
            mesh_group = ob_groups.get(mesh_name)
            if mesh_group is None:
                mesh_group = ob_groups[mesh_name] = []
            mesh_group.append(ob)

    material_settings = {}
    for mat in bpy.data.materials:
        output_material_node = get_output_material_node(mat)
        node_group = get_linked_node(output_material_node, "Surface", "GROUP")
        if node_group and node_group.node_tree.name in SHADER_NODE_NAMES:
            material_settings[mat.name] = {"is_fullbright": node_group.inputs["Is Fullbright"].default_value, 
                                           "use_shine": node_group.inputs["Use Shine"].default_value, 
                                           "use_specular_mask": node_group.inputs["Use Specular Mask"].default_value, 
                                           "use_normal": node_group.inputs["Use Normal"].default_value}

            node_group.inputs["Is Fullbright"].default_value = True
            node_group.inputs["Use Shine"].default_value = False
            node_group.inputs["Use Specular Mask"].default_value = False
            node_group.inputs["Use Normal"].default_value = False

    bpy.ops.object.select_all(action='DESELECT')
    for mesh_name, ob_group in ob_groups.items():
        mesh = ob_group[0].data
        used_materials = get_used_materials(mesh)
        for ob_idx, ob in enumerate(ob_group):
            area = get_object_surface_area(ob, depsgraph)
            res = compute_lightmap_resolution(area)
            res = max(32, min(4096, res))

            image_name = "%s_lm%s" % (ob.data.name, ob_idx)

            ob.cb.lightmap_name_override = image_name

            image = bpy.data.images.get(image_name)
            if image and image.has_data:
                image.scale(res, res)
            else:
                image = bpy.data.images.new(image_name, width=res, height=res)

            for mat in used_materials:
                lightmap_node = None
                output_material_node = get_output_material_node(mat)

                node_group = get_linked_node(output_material_node, "Surface", "GROUP")
                if node_group and node_group.node_tree.name in SHADER_NODE_NAMES:
                    lightmap_node = get_linked_node(node_group, "Light Map", "TEX_IMAGE")
                    if lightmap_node is not None:
                        for link in node_group.inputs["Light Map"].links:
                            mat.node_tree.links.remove(link)

                if lightmap_node is None:
                    for node in mat.node_tree.nodes:
                        if node.type == 'TEX_IMAGE':
                            img = node.image
                            if not img:
                                continue

                            if img.source == 'FILE' and img.filepath:
                                filename = os.path.basename(bpy.path.abspath(img.filepath))
                                if "_lm" in filename.lower():
                                    lightmap_node = node
                                    break

                            elif img.source == 'GENERATED':
                                filename = os.path.basename(bpy.path.abspath(img.name))
                                if "_lm" in filename.lower():
                                    lightmap_node = node
                                    break

                if lightmap_node is None:
                    lightmap_node = mat.node_tree.nodes.new("ShaderNodeTexImage")
                    lightmap_node.location = (-720.0, -320.0)

                lightmap_node.image = image
                lightmap_node.select = True

            run_bake(context, ob, generate_vertex_colors=ob.cb.is_per_vertex)

            for mat in used_materials:
                output_material_node = get_output_material_node(mat)

                node_group = get_linked_node(output_material_node, "Surface", "GROUP")
                if node_group and node_group.node_tree.name in SHADER_NODE_NAMES and not node_group.inputs["Diffuse Map Alpha"].is_linked:
                    lightmap_node = None
                    for node in mat.node_tree.nodes:
                        if node.type == 'TEX_IMAGE':
                            img = node.image
                            if not img:
                                continue

                            if img.source == 'FILE' and img.filepath:
                                filename = os.path.basename(bpy.path.abspath(img.filepath))
                                if "_lm" in filename.lower():
                                    lightmap_node = node
                                    break

                            elif img.source == 'GENERATED':
                                filename = os.path.basename(bpy.path.abspath(img.name))
                                if "_lm" in filename.lower():
                                    lightmap_node = node
                                    break

                    if lightmap_node is not None:
                        connect_inputs(mat.node_tree, lightmap_node, "Color", node_group, "Light Map")

            if not ob.cb.is_per_vertex:
                save_path = os.path.join(bpy.path.abspath("//"), "lightmaps", f"{image_name}.png")
                os.makedirs(os.path.dirname(save_path), exist_ok=True)

                image.filepath_raw = save_path
                image.file_format = 'PNG'
                image.save_render(save_path)

    for mat in bpy.data.materials:
        mat_settings = material_settings.get(mat.name)
        if mat_settings is not None:
            output_material_node = get_output_material_node(mat)
            node_group = get_linked_node(output_material_node, "Surface", "GROUP")
            if node_group and node_group.node_tree.name in SHADER_NODE_NAMES:
                node_group.inputs["Is Fullbright"].default_value = mat_settings["is_fullbright"]
                node_group.inputs["Use Shine"].default_value = mat_settings["use_shine"]
                node_group.inputs["Use Specular Mask"].default_value = mat_settings["use_specular_mask"]
                node_group.inputs["Use Normal"].default_value = mat_settings["use_normal"]

    bpy.ops.wm.console_toggle()
