import bpy

from math import radians, cos, sin
from bpy_extras.io_utils import unpack_list
from mathutils import Euler, Matrix, Vector

def flip(v):
    return ((v[0],v[2],v[1]) if len(v)<4 else (v[0], v[1],v[3],v[2]))

def flip_all(v):
    return [y for y in [flip(x) for x in v]]

def import_mesh(node, material_mapping, bm):
    mesh = bpy.data.meshes.new("temp_mesh")

    # join face arrays
    faces = []
    for face in node.faces:
        faces.extend(face.indices)

    pivot_matrix = Matrix.Rotation(radians(90), 4, 'X') @  Matrix.Diagonal((-1.0, 1.0, 1.0, 1.0))
    vertices = [pivot_matrix @ Vector(vertex) for vertex in node.vertices]

    # create mesh from data
    mesh.from_pydata(vertices, [], flip_all(faces))
    for poly in mesh.polygons:
        poly.use_smooth = True

    # assign normals
    mesh.vertices.foreach_set('normal', unpack_list(node.normals))

    # assign uv coordinates
    uvs = [(0,0) if len(uv)==0 else (uv[0], 1-uv[1]) for uv in node.uvs]
    uvlist = [i for poly in mesh.polygons for vidx in poly.vertices for i in uvs[vidx]]
    mesh.uv_layers.new().data.foreach_set('uv', uvlist)

    # adding object materials (insert-ordered)
    for key, value in material_mapping.items():
        mesh.materials.append(bpy.data.materials[value])

    # assign material_indexes
    poly = 0
    for face in node.faces:
        for _ in face.indices:
            mesh.polygons[poly].material_index = face.brush_id
            poly += 1

    bm.from_mesh(mesh)
    bpy.data.meshes.remove(mesh)

def import_node_recursive(node, material_mapping, bm):
    if 'vertices' in node and 'faces' in node:
        import_mesh(node, material_mapping, bm)

    for x in node.nodes:
        import_node_recursive(x, material_mapping, bm)
