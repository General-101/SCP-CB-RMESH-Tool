import os
import bpy

from pathlib import Path
from mathutils import Matrix, Vector, Quaternion
from .process_x import write_x, read_x
from .common_functions import (RandomColorGenerator,
                               MaterialType,
                               get_file,
                               is_string_empty,
                               flip,
                               get_output_material_node,
                               get_shader_node,
                               connect_inputs,
                               clean_string,
                               generate_texture_mapping,
                               SHADER_RESOURCES,
                               SHADER_NODE_NAMES)

def generate_materials(materials_dict, random_color_gen, mesh, is_simple, ob_data, local_asset_path, error_log, material_type_enum, material_list=None):
    for material_idx, material_dict in enumerate(materials_dict):
        material_name = ""
        if material_dict["name"] is None:
            material_name = "materIal_%s" % material_idx
        else:
            material_name = material_dict["name"]

        material = bpy.data.materials.new(name=material_name)
        material.diffuse_color = random_color_gen.next()

        if mesh is not None:
            mesh.materials.append(material)

        if is_simple:
            ob_data.materials.append(material)

        if bpy.app.version <= (5,0,0):
            material.use_nodes = True

        material.node_tree.nodes.clear()

        output_material_node = get_output_material_node(material)
        output_material_node.location = Vector((0.0, 0.0))

        sr, sg, sb = material_dict["specular"]
        er, eg, eb = material_dict["emissive"]
        if material_type_enum == MaterialType.simple:
            bsdf_node = material.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
            bsdf_node.name = "Principled BSDF"
            bsdf_node.location = (-440.0, 0.0)
            connect_inputs(material.node_tree, bsdf_node, "BSDF", output_material_node, "Surface")

            dr, dg, db, da = material_dict["diffuse"]
            bsdf_node.inputs["Base Color"].default_value = (dr, dg, db, da)
            bsdf_node.inputs["Alpha"].default_value = da
            bsdf_node.inputs["Specular IOR Level"].default_value = sr
            bsdf_node.inputs["Emission Color"].default_value = (er, eg, eb, 1.0)

            shader_input_node = bsdf_node
            shader_color_input = "Base Color"
            shader_emission_input = "Emission Color"

        else:
            x_node = get_shader_node(material.node_tree, SHADER_RESOURCES, "cb_material")
            x_node.name = "X Material"
            x_node.location = (-440.0, 0.0)
            connect_inputs(material.node_tree, x_node, "Shader", output_material_node, "Surface")

            x_node.inputs["Diffuse Overlay"].default_value = material_dict["diffuse"]
            x_node.inputs["Emission Strength"].default_value = material_dict["power"]
            x_node.inputs["Specular Map"].default_value = (sr, sg, sb, 1)
            x_node.inputs["Emission Map"].default_value = (er, eg, eb, 1)

            shader_input_node = x_node
            shader_color_input = "Diffuse Map"
            shader_emission_input = "Emission Map"

        texture_node = get_file(material_dict["texture"], True, True, directory_path=local_asset_path)
        if texture_node:
            texture = material.node_tree.nodes.new("ShaderNodeTexImage")
            texture.location = (-720.0, 0)
            texture.image = texture_node
            connect_inputs(material.node_tree, texture, "Color", shader_input_node, shader_color_input)

            mapping_node, uv_node = generate_texture_mapping(material.node_tree, texture)
            uv_node.uv_map = "uvmap_render"
            mapping_node.vector_type = 'TEXTURE'

            texture_name = os.path.basename(material_dict["texture"]).rsplit(".", 1)[0]
            texture_bump_data = get_file("%sbump" % texture_name, directory_path=local_asset_path)
            texture_glow_data = get_file("%sglow" % texture_name, directory_path=local_asset_path)
            if texture_bump_data:
                texture_bump = material.node_tree.nodes.new("ShaderNodeTexImage")
                texture_bump.image = texture_bump_data
                texture_bump.image.alpha_mode = 'CHANNEL_PACKED'
                texture_bump.interpolation = 'Cubic'
                texture_bump.image.colorspace_settings.name = 'Non-Color'
                texture_bump.location = (-720.0, -380)
                
                if material_type_enum == MaterialType.simple:
                    normal_map_node = material.node_tree.nodes.new("ShaderNodeNormalMap")
                    normal_map_node.location = (-720.0, -380)
                    connect_inputs(material.node_tree, texture_bump, "Color", normal_map_node, "Color")
                    connect_inputs(material.node_tree, normal_map_node, "Normal", shader_input_node, "Normal")

                else:
                    connect_inputs(material.node_tree, texture_bump, "Color", shader_input_node, "Normal Map")

                mapping_node, uv_node = generate_texture_mapping(material.node_tree, texture_bump)
                uv_node.uv_map = "uvmap_render"
                mapping_node.vector_type = 'TEXTURE'

            if texture_glow_data:
                texture_glow = material.node_tree.nodes.new("ShaderNodeTexImage")
                texture_glow.image = texture_glow_data
                texture_glow.image.alpha_mode = 'CHANNEL_PACKED'
                texture_glow.location = (-720.0, -760)
                connect_inputs(material.node_tree, texture_glow, "Color", shader_input_node, shader_emission_input)

                mapping_node, uv_node = generate_texture_mapping(material.node_tree, texture_glow)
                uv_node.uv_map = "uvmap_render"
                mapping_node.vector_type = 'TEXTURE'

        else:
            if material_dict["texture"] is not None:
                error_log.add('Failed to retrive "%s"' % material_dict["texture"])

        if material_list is not None:
            material_list.append(material)

def create_object(arm_ob, parent_bone, x_dict, mesh_dict, room_scale, material_type_enum, ob_data=None, is_simple=False, world_transform=None, material_list=[], local_asset_path="", error_log=set(), random_color_gen=None):
    loop_normals = []
    mesh_name = mesh_dict["name"]
    if mesh_name == None:
        if parent_bone is not None:
            mesh_name = parent_bone.name
        else:
            mesh_name = "mesh"

    vertices = [room_scale * Vector(flip(vertex)) for vertex in mesh_dict["vertices"]]
    triangles = [triangle[::-1] for triangle in mesh_dict["faces"]]
    mesh = bpy.data.meshes.new(mesh_name)
    mesh.from_pydata(vertices, [], triangles)
    mesh.validate(clean_customdata=True)

    if not is_simple:
        object_mesh = bpy.data.objects.new(mesh_name, mesh)
        bpy.context.collection.objects.link(object_mesh)
        object_mesh.parent = arm_ob
    else:
        if world_transform is not None:
            mesh.transform(world_transform)

    uv_render = mesh.uv_layers.new(name="uvmap_render")
    for poly_idx, poly in enumerate(mesh.polygons):
        poly.use_smooth = True

    if not x_dict["xof_header"] == "xof 0302txt 0064":
        generate_materials(mesh_dict["materials"], random_color_gen, mesh, is_simple, ob_data, local_asset_path, error_log, material_type_enum)

    else:
        for mat in material_list:
            mesh.materials.append(mat)
            if is_simple:
                ob_data.materials.append(mat)

    if x_dict["xof_header"] == "xof 0302txt 0064":
        for mat_data_idx, material_face in enumerate(mesh_dict["material_indices"]):
            material_index = 0
            material_data = mesh_dict["materials"][mat_data_idx]
            for mat_idx, material in enumerate(x_dict["materials"]):
                if material["name"] == material_data["name"]:
                    material_index = mat_idx

            mesh.polygons[material_face].material_index = material_index

    for poly_idx, poly in enumerate(mesh.polygons):
        if not x_dict["xof_header"] == "xof 0302txt 0064":
            poly.material_index = mesh_dict["material_indices"][poly_idx]

        for loop_index in poly.loop_indices:
            vert_index = mesh.loops[loop_index].vertex_index
            if not x_dict["xof_header"] == "xof 0302txt 0064":
                loop_normals.append(Vector(flip(mesh_dict["normals"][vert_index])))

            u, v = mesh_dict["texcoords"][vert_index]
            uv_render.data[loop_index].uv = (u, 1 - v)

    if not is_simple:
        for skin_weight in mesh_dict["skin_weights"]:
            group_name = skin_weight["bone"]
            if not group_name in object_mesh.vertex_groups.keys():
                object_mesh.vertex_groups.new(name = group_name)

            for skin_idx, skin_element in enumerate(skin_weight["indices"]):
                group_index = object_mesh.vertex_groups.keys().index(group_name)
                object_mesh.vertex_groups[group_index].add([skin_element], skin_weight["weights"][skin_idx], 'ADD')

    if not x_dict["xof_header"] == "xof 0302txt 0064":
        mesh.normals_split_custom_set(loop_normals)

    entity_mesh = mesh
    if not is_simple:
        entity_mesh = object_mesh

    return entity_mesh

def x_matrix_to_blender(mat, room_scale):
    loc, rot, scl = Matrix((mat[0:4], mat[4:8], mat[8:12], mat[12:16])).transposed().decompose()
    return Matrix.LocRotScale(room_scale * Vector(flip(loc)), Quaternion(flip(rot)).inverted(), Vector(flip(scl)))

def blender_matrix_to_x(mat, room_scale):
    loc, rot, scl = mat.decompose()
    b_matrix = Matrix.LocRotScale((1.0 / room_scale) * Vector(flip(loc)), Quaternion(flip(rot)).inverted(), Vector(flip(scl))).transposed()
    matrix_array = []
    for row in b_matrix:
        for element in row:
            matrix_array.append(element)

    return matrix_array

def create_bone(filepath, rigid_obs, arm_ob, x_dict, frame, room_scale, material_type_enum, parent_bone=None, bm=None, ob_data=None, is_simple=False, material_list=[], local_asset_path="", error_log=set(), random_color_gen=None):
    name = frame["name"]
    world_transform = x_matrix_to_blender(frame["transform"], room_scale)

    bone = None
    bone_name = None
    if not is_simple:
        bone = arm_ob.data.edit_bones.new(name)
        bone_name = bone.name
        if parent_bone:
            bone.head = parent_bone.tail
        else:
            bone.head = (0, 0, 0)

        bone.tail = bone.head + Vector((0, 0.1, 0))
        if parent_bone:
            bone.parent = parent_bone

        bone.matrix = world_transform

    for mesh_dict in frame["meshes"]:
        object_mesh = create_object(arm_ob, bone, x_dict, mesh_dict, room_scale, material_type_enum, ob_data, is_simple, world_transform, material_list, local_asset_path, error_log, random_color_gen)
        if is_simple:
            bm.from_mesh(object_mesh)
            bpy.data.meshes.remove(object_mesh)

        rigid_obs.append([object_mesh, bone_name, world_transform])

    for child in frame.get("children", []):
        create_bone(filepath, rigid_obs, arm_ob, x_dict, child, room_scale, material_type_enum, bone, bm, ob_data, is_simple, material_list, local_asset_path, error_log, random_color_gen)

def get_linked_node(node, input_name, search_type):
    linked_node = None
    node_input = node.inputs[input_name]
    if node_input.is_linked:
        for node_link in node_input.links:
            if node_link.from_node.type == search_type:
                linked_node = node_link.from_node
                break

    return linked_node

def get_skeleton_tree(active_ob, frame_dict, bone_transforms, rigid_ob_dict, depsgraph, room_scale, parent_bone=None):
    for bone in active_ob.pose.bones:
        if bone.parent == parent_bone:
            bone_dict = {
                "name": clean_string(bone.name),
                "transform": [],
                "meshes": [],
                "children": []
            }

            rigid_obs = rigid_ob_dict.get(bone.name)
            if rigid_obs is not None:
                for rigid_ob in rigid_obs:
                    process_mesh(bone_dict["meshes"], bone_transforms, active_ob, rigid_ob, depsgraph, room_scale, bone)

            bone_dict["transform"] = blender_matrix_to_x(bone_transforms.get(bone.name), room_scale)
            get_skeleton_tree(active_ob, bone_dict["children"], bone_transforms, rigid_ob_dict, depsgraph, room_scale, bone)

            frame_dict.append(bone_dict)

def process_mesh(ob_dict, bone_transforms, armature, ob, depsgraph, room_scale, bone=None):
    ob_eval = ob.evaluated_get(depsgraph)
    mesh = ob_eval.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
    mesh.calc_loop_triangles()
    mesh.transform(ob.matrix_world)
    if bone is not None:
        mesh.transform((armature.matrix_world @ bone.matrix).inverted())

    uv_layer = None
    uv_count = len(mesh.uv_layers)
    if mesh.uv_layers.active:
        uv_layer = mesh.uv_layers.active
    if uv_count > 0:
        uv_layer = mesh.uv_layers[0]

    mesh_dict = {
        "name": clean_string(ob.name),
        "vertices": [],
        "faces": [],
        "normals": [],
        "normal_indices": [],
        "texcoords": [],
        "dup_preexport_count": 0,
        "dup_indices": [],
        "material_indices": [],
        "materials": [],
        "max_weights_per_vertex": 1,
        "max_weights_per_face": 1,
        "group_count": 0,
        "skin_weights": []
    }

    mesh_dict["dup_preexport_count"] = len(mesh.vertices)

    original_vertex_map = {}
    original_vertices = []
    vertex_map = {}
    for tri in mesh.loop_triangles:
        tri_indices = []
        mat_idx = tri.material_index
        mesh_dict["material_indices"].append(mat_idx)
        for loop_index in tri.loops:
            mat_index = tri.material_index

            loop = mesh.loops[loop_index]
            v = mesh.vertices[loop.vertex_index]
            loop_normal = flip(loop.normal)

            pos = (1.0 / room_scale) * Vector(flip(v.co))

            uv = (0.0, 0.0)
            if uv_layer:
                u0, v0 = uv_layer.data[loop_index].uv
                uv = (u0, 1 - v0)

            pos_key = (round(pos.x, 6), round(pos.y, 6), round(pos.z, 6))

            if pos_key not in original_vertex_map:
                original_vertex_map[pos_key] = len(original_vertices)
                original_vertices.append(pos_key)

            original_index = original_vertex_map[pos_key]

            expanded_key = (pos_key, uv, loop_normal, mat_index)

            if expanded_key not in vertex_map:
                vertex_map[expanded_key] = len(mesh_dict["vertices"])
                mesh_dict["vertices"].append(pos)
                mesh_dict["texcoords"].append(uv)
                mesh_dict["normals"].append(loop_normal)
                mesh_dict["dup_indices"].append(original_index)

            tri_indices.append(vertex_map[expanded_key])

        mesh_dict["faces"].append(tri_indices[::-1])
        mesh_dict["normal_indices"].append(tri_indices[::-1])

    if ob.parent_type == 'BONE':
        bone_dict = {
            "bone": None,
            "indices": [],
            "weights": [],
            "transform": []
            }

        valid_length = len(ob.parent_bone) > 0
        bone_exists = False
        for bone in armature.data.bones:
            if bone.name == ob.parent_bone:
                bone_exists = True

        if valid_length and bone_exists:
            bone_name = ob.parent_bone
        else:
            bone_name = armature.data.bones[0]

        vert_count = len(mesh_dict["vertices"])
        bone_dict["bone"] = bone_name
        bone_dict["indices"] = [idx for idx in range(vert_count)]
        bone_dict["weights"] = [1.0 for idx in range(vert_count)]
        bone_dict["transform"] = blender_matrix_to_x(bone_transforms.get(bone_name), room_scale)
        mesh_dict["skin_weights"].append(bone_dict)

    mesh_dict["group_count"] = len(mesh_dict["skin_weights"])
    for slot in ob.material_slots:
        material_dict = {"name": None,
                        "diffuse": (0.0, 0.0, 0.0, 0.0),
                        "power": 0.0,
                        "specular": (0.0, 0.0, 0.0),
                        "emissive": (0.0, 0.0, 0.0),
                        "texture": None
                        }

        mat = slot.material
        if mat is not None:
            output_material_node = get_output_material_node(mat)
            bdsf_principled = get_linked_node(output_material_node, "Surface", "BSDF_PRINCIPLED")
            node_group = get_linked_node(output_material_node, "Surface", "GROUP")
            if node_group and node_group.node_tree.name in SHADER_NODE_NAMES:
                image_node = get_linked_node(node_group, "Diffuse Map", "TEX_IMAGE")
                dr, dg, db, da = node_group.inputs["Diffuse Overlay"].default_value
                sr, sg, sb, sa = node_group.inputs["Specular Map"].default_value
                er, eg, eb, ea = node_group.inputs["Emission Map"].default_value

                material_dict["name"] = clean_string(mat.name)
                material_dict["diffuse"] = (dr, dg, db, da)
                material_dict["power"] = node_group.inputs["Emission Strength"].default_value
                material_dict["specular"] = (sr, sg, sb)
                material_dict["emissive"] = (er, eg, eb)
                if image_node and image_node.image:
                    material_dict["texture"] = os.path.basename(bpy.path.abspath(image_node.image.filepath))

            elif bdsf_principled:
                dr, dg, db, da = bdsf_principled.inputs["Base Color"].default_value
                da = bdsf_principled.inputs["Alpha"].default_value
                sr = sg = sb = bdsf_principled.inputs["Specular IOR Level"].default_value
                er, eg, eb, ea = bdsf_principled.inputs["Emission Color"].default_value
                image_node = get_linked_node(bdsf_principled, "Base Color", "TEX_IMAGE")

                material_dict["name"] = clean_string(mat.name)
                material_dict["diffuse"] = (dr, dg, db, da)
                material_dict["power"] = bdsf_principled.inputs[28].default_value
                material_dict["specular"] = (sr, sg, sb)
                material_dict["emissive"] = (er, eg, eb)
                if image_node and image_node.image:
                    material_dict["texture"] = os.path.basename(bpy.path.abspath(image_node.image.filepath))

        mesh_dict["materials"].append(material_dict)

    ob_dict.append(mesh_dict)

def export_scene(context, output_path, report):
    room_scale = bpy.context.preferences.addons[__package__].preferences.room_scale
    if context.view_layer.objects.active is not None:
        bpy.ops.object.mode_set(mode='OBJECT')

    armature_ob = None
    if context.object and context.object.type == 'ARMATURE' and len(context.object.data.bones) > 0:
        armature_ob = context.object

    if armature_ob is None:
        for ob in bpy.context.view_layer.objects:
            if ob.type == 'ARMATURE' and len(ob.data.bones) > 0:
                context.view_layer.objects.active = ob
                armature_ob = ob
                break

    if armature_ob:
        x_dict = {
            "xof_header": None,
            "templates": [],
            "anim_ticks_per_second": None,
            "materials": [],
            "frames": [],
            "meshes": [],
            "animation_set": []
        }

        x_dict["xof_header"] = "xof 0303txt 0032"

        skinned_ob_list = []
        rigid_ob_dict = {}

        armature_ob.data.pose_position = 'REST'
        depsgraph = context.evaluated_depsgraph_get()
        for ob in bpy.context.view_layer.objects:
            if ob.type == "MESH":
                if ob.parent_type == 'OBJECT' and ob.parent == armature_ob:
                    skinned_ob_list.append(ob)

                elif ob.parent_type == 'BONE' and ob.parent == armature_ob and len(ob.parent_bone) > 0:
                    rigid_ob_list = rigid_ob_dict.get(ob.parent_bone)
                    if rigid_ob_list is None:
                        rigid_ob_list = rigid_ob_dict[ob.parent_bone] = []

                    rigid_ob_list.append(ob)

        bone_transforms = {}
        for bone in armature_ob.data.bones:
            bone_transforms[bone.name] = armature_ob.matrix_world @ bone.matrix_local

        bpy.ops.object.mode_set(mode = 'POSE')
        get_skeleton_tree(armature_ob, x_dict["frames"], bone_transforms, rigid_ob_dict, depsgraph, room_scale, None)
        bpy.ops.object.mode_set(mode = 'OBJECT')

        for skinned_ob in skinned_ob_list:
            process_mesh(x_dict["meshes"], bone_transforms, armature_ob, skinned_ob, depsgraph, room_scale)

        write_x(x_dict, output_path)
        armature_ob.data.pose_position = 'POSE'

    else:
        report({'ERROR'}, "No armature selected. Export will now be aborted")
        return {'CANCELLED'}

    report({'INFO'}, "Export completed successfully")
    return {'FINISHED'}

def import_scene(context, filepath, report, bm=None, ob_data=None, is_simple=False, error_log=None, random_color_gen=None):
    material_list = []
    x_dict = read_x(filepath)
    if x_dict:
        if error_log is None:
            error_log = set()
        if random_color_gen is None:
            random_color_gen = RandomColorGenerator() # generates a random sequence of colors

        game_path = Path(bpy.context.preferences.addons["io_scene_cb"].preferences.game_path)
        room_scale = bpy.context.preferences.addons[__package__].preferences.room_scale
        material_type_enum = MaterialType(int(bpy.context.preferences.addons[__package__].preferences.material_type))

        local_asset_path = ""
        if not is_string_empty(str(game_path)) and str(filepath).startswith(str(game_path)):
            local_asset_path = os.path.dirname(os.path.relpath(str(filepath), str(game_path)))

        arm_ob = None
        if not is_simple:
            arm_data = bpy.data.armatures.new("Armature")
            arm_ob = bpy.data.objects.new("Armature", arm_data)
            context.collection.objects.link(arm_ob)

            context.view_layer.objects.active = arm_ob
            bpy.ops.object.mode_set(mode='EDIT')

        if x_dict["xof_header"] == "xof 0302txt 0064":
            generate_materials(x_dict["materials"], random_color_gen, None, is_simple, ob_data, local_asset_path, error_log, material_type_enum, material_list)

        rigid_obs = []
        for bone in x_dict["frames"]:
            create_bone(filepath, rigid_obs, arm_ob, x_dict, bone, room_scale, material_type_enum, None, bm, ob_data, is_simple, material_list, local_asset_path, error_log, random_color_gen)

        if not is_simple:
            bpy.ops.object.mode_set(mode='OBJECT')
            context.view_layer.update()
            for rigid_ob in rigid_obs:
                object_mesh, parent_bone_name, transform = rigid_ob
                object_mesh.parent_type = 'BONE'
                object_mesh.parent_bone = parent_bone_name
                object_mesh.matrix_world = transform

        if not x_dict["xof_header"] == "xof 0302txt 0064":
            for mesh_dict in x_dict["meshes"]:
                object_mesh = create_object(arm_ob, None, x_dict, mesh_dict, room_scale, material_type_enum, ob_data, is_simple, None, material_list, local_asset_path, error_log, random_color_gen)
                if is_simple:
                    bm.from_mesh(object_mesh)
                    bpy.data.meshes.remove(object_mesh)

        if not is_simple:
            for error in error_log:
                report({'WARNING'}, error)

    report({'INFO'}, "Import completed successfully")
    return {'FINISHED'}
