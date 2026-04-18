import os
import bpy

from pathlib import Path
from .process_smf import read_smf
from mathutils import Matrix, Vector, Quaternion, Euler
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
                               SHADER_RESOURCES)

def import_mesh(data, node, random_color_gen, local_asset_path, room_scale):
    vertices = [room_scale * Vector(flip(vertex)) for vertex in node["vertices"]]
    mesh = bpy.data.meshes.new("mesh")
    mesh.from_pydata(vertices, [], node["faces"])

    # This is for some reason fixing a crash I get when I set custom normals. - Gen
    mesh.validate(clean_customdata=True)

    material = bpy.data.materials.new("material_%s" % data["ob_index"])
    mesh.materials.append(material)
    material.diffuse_color = random_color_gen.next()

    material.use_nodes = True
    for mat_node in material.node_tree.nodes:
        material.node_tree.nodes.remove(mat_node)

    output_material_node = get_output_material_node(material)
    output_material_node.location = Vector((0.0, 0.0))

    smf_node = get_shader_node(material.node_tree, SHADER_RESOURCES, "cb_material")
    smf_node.name = "smf Material"
    smf_node.location = (-440.0, 0.0)

    connect_inputs(material.node_tree, smf_node, "Shader", output_material_node, "Surface")
    texture_asset = get_file(os.path.basename(node['texture_name']), True, True, directory_path=local_asset_path)
    if texture_asset:
        texture_node = material.node_tree.nodes.new('ShaderNodeTexImage')
        texture_node.image = texture_asset

        texture_node.location = (-720.0, -380)
        connect_inputs(material.node_tree, texture_node, "Color", smf_node, "Diffuse Map")

        mapping_node, uv_node = generate_texture_mapping(material.node_tree, texture_node)
        uv_node.uv_map = "uvmap_render"
        mapping_node.vector_type = 'TEXTURE'

        texture_name = os.path.basename(node['texture_name']).rsplit(".", 1)[0]
        texture_bump_data = get_file("%sbump" % texture_name, directory_path=local_asset_path)
        texture_glow_data = get_file("%sglow" % texture_name, directory_path=local_asset_path)
        if texture_bump_data:
            texture_bump = material.node_tree.nodes.new("ShaderNodeTexImage")
            texture_bump.image = texture_bump_data
            texture_bump.image.alpha_mode = 'CHANNEL_PACKED'
            texture_bump.interpolation = 'Cubic'
            texture_bump.image.colorspace_settings.name = 'Non-Color'
            texture_bump.location = (-720.0, -760)
            connect_inputs(material.node_tree, texture_bump, "Color", smf_node, "Normal Map")

            mapping_node, uv_node = generate_texture_mapping(material.node_tree, texture_bump)
            uv_node.uv_map = "uvmap_render"
            mapping_node.vector_type = 'TEXTURE'

        if texture_glow_data:
            texture_glow = material.node_tree.nodes.new("ShaderNodeTexImage")
            texture_glow.image = texture_glow_data
            texture_glow.image.alpha_mode = 'CHANNEL_PACKED'
            texture_glow.location = (-720.0, -1140)
            connect_inputs(material.node_tree, texture_glow, "Color", smf_node, "Emission Map")

            mapping_node, uv_node = generate_texture_mapping(material.node_tree, texture_glow)
            uv_node.uv_map = "uvmap_render"
            mapping_node.vector_type = 'TEXTURE'

    loop_normals = []
    layer_uv_0 = mesh.uv_layers.new(name="uvmap_render")
    for poly_idx, poly in enumerate(mesh.polygons):
        poly.use_smooth = True
        for loop_index in poly.loop_indices:
            vert_index = mesh.loops[loop_index].vertex_index
            loop_normals.append(flip(node["normals"][vert_index]))
            u0, v0 = node["uvs"][vert_index]

            layer_uv_0.data[loop_index].uv = (u0, 1 - v0)

    mesh.normals_split_custom_set(loop_normals)

    return mesh

def import_node_recursive(context, data, node, random_color_gen, local_asset_path, room_scale, parent_ob=None):
    ob_index = data.get("ob_index")
    if ob_index is None:
        data["ob_index"] = 0

    mesh_data = import_mesh(data, node, random_color_gen, local_asset_path, room_scale)
    ob_data = bpy.data.objects.new("node_%s" % data["ob_index"], mesh_data)
    context.collection.objects.link(ob_data)

    data["ob_index"] += 1

    if parent_ob:
        ob_data.parent = parent_ob

    node_transform = Matrix.LocRotScale(room_scale * Vector(flip(node["position"])), Euler(node["rotation"]), Vector(flip(node["scale"])))
    ob_data.matrix_local = node_transform
    for child_node in node["nodes"]:
        import_node_recursive(context, data, child_node, random_color_gen, local_asset_path, room_scale, ob_data)

def import_scene(context, filepath, report):
    game_path = Path(bpy.context.preferences.addons[__package__].preferences.game_path)
    room_scale = bpy.context.preferences.addons[__package__].preferences.room_scale

    local_asset_path = ""
    if not is_string_empty(str(game_path)) and str(filepath).startswith(str(game_path)):
        local_asset_path = os.path.dirname(os.path.relpath(str(filepath), str(game_path)))

    data = read_smf(filepath)

    error_log = set()
    random_color_gen = RandomColorGenerator() # generates a random sequence of colors

    for child_node in data["nodes"]:
        import_node_recursive(context, data, child_node, random_color_gen, local_asset_path, room_scale)

    report({'INFO'}, "Import completed successfully")
    return {'FINISHED'}
