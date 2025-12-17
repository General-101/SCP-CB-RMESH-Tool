# ##### BEGIN MIT LICENSE BLOCK #####
#
# MIT License
#
# Copyright (c) 2023 Steven Garcia
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# ##### END MIT LICENSE BLOCK #####

bl_info = {
    "name": "SCP CB Toolset",
    "author": "General_101",
    "version": (1, 0, 0),
    "blender": (5, 0, 0),
    "location": "File > Import-Export",
    "description": "Import-Export SCP CB RMESH files",
    "warning": "",
    "support": 'COMMUNITY',
    "category": "Import-Export"}

import bpy

from bpy.types import Operator
from bpy.props import StringProperty
from bpy_extras.io_utils import (
    ImportHelper,
    ExportHelper
    )

if (4, 1, 0) <= bpy.app.version:
    from bpy.types import FileHandler

class SCPCBAddonPrefs(bpy.types.AddonPreferences):
    bl_idname = __name__
    game_path: StringProperty(
        name="Game Path",
        description="Path to the game directory",
        subtype="DIR_PATH"
    )

    def draw(self, context):
        layout = self.layout

        box = layout.box()
        box.label(text="Addon Options:")
        col = box.column(align=True)
        row = col.row()
        row.label(text='Game Path:')
        row.prop(self, "game_path", text='')

class ExportRMESH(Operator, ExportHelper):
    """Write an RMESH file"""
    bl_idname = 'export_scene.ermesh'
    bl_label = 'Export RMESH'
    filename_ext = '.rmesh'

    filter_glob: StringProperty(
        default="*.rmesh",
        options={'HIDDEN'},
        )

    def execute(self, context):
        from . import scene_rmesh

        return scene_rmesh.export_scene(context, self.filepath, self.report)

class ImportRMESH(Operator, ImportHelper):
    """Import an RMESH file"""
    bl_idname = "import_scene.irmesh"
    bl_label = "Import RMESH"
    filename_ext = '.rmesh'

    filter_glob: StringProperty(
        default="*.rmesh",
        options={'HIDDEN'},
        )

    filepath: StringProperty(
        subtype='FILE_PATH', 
        options={'SKIP_SAVE'}
        )

    def execute(self, context):
        from . import scene_rmesh

        return scene_rmesh.import_scene(context, self.filepath, self.report)

    if (4, 1, 0) <= bpy.app.version:
        def invoke(self, context, event):
            if self.filepath:
                return self.execute(context)
            context.window_manager.fileselect_add(self)
            return {'RUNNING_MODAL'}

if (4, 1, 0) <= bpy.app.version:
    class ImportRMESH_FileHandler(FileHandler):
        bl_idname = "RMESH_FH_import"
        bl_label = "File handler for RMESH import"
        bl_import_operator = "import_scene.rmesh"
        bl_file_extensions = ".rmesh"

        @classmethod
        def poll_drop(cls, context):
            return (context.area and context.area.type == 'VIEW_3D')

def menu_func_export(self, context):
    self.layout.operator(ExportRMESH.bl_idname, text='SCP RMESH (.rmesh)')

def menu_func_import(self, context):
    self.layout.operator(ImportRMESH.bl_idname, text='SCP RMESH (.rmesh)')

classesscp = [
    ImportRMESH,
    ExportRMESH
]

if (4, 1, 0) <= bpy.app.version:
    classesscp.append(ImportRMESH_FileHandler)

def register():
    bpy.utils.register_class(SCPCBAddonPrefs)
    for clsscp in classesscp:
        bpy.utils.register_class(clsscp)

    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)

def unregister():
    bpy.utils.unregister_class(SCPCBAddonPrefs)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    for clsscp in classesscp:
        bpy.utils.unregister_class(clsscp)

if __name__ == '__main__':
    register()
