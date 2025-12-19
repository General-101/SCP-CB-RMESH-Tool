bl_info = {
    "name": "SCP UER Toolset",
    "author": "General_101",
    "version": (1, 0, 0),
    "blender": (5, 0, 0),
    "location": "File > Import-Export",
    "description": "Import-Export SCP UER RMESH files",
    "warning": "",
    "support": 'COMMUNITY',
    "category": "Import-Export"}

import bpy

from bpy.types import (
        PropertyGroup,
        Operator,
        Panel
        )
from bpy.props import (
        IntProperty,
        BoolProperty,
        EnumProperty,
        StringProperty,
        PointerProperty,
        CollectionProperty
        )
from bpy_extras.io_utils import (
    ImportHelper,
    ExportHelper
    )

from enum import Flag, Enum, auto
if (4, 1, 0) <= bpy.app.version:
    from bpy.types import FileHandler

class ObjectType(Enum):
    mesh = 0
    collision = auto()
    entity_screen = auto()
    entity_save_screen = auto()
    entity_waypoint = auto()
    entity_light = auto()
    entity_light_fix = auto()
    entity_spotlight = auto()
    entity_sound_emitter = auto()
    entity_model = auto()
    entity_mesh = auto()

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

class RMESHObjectPropertiesGroup(PropertyGroup):
    object_type: EnumProperty(
        name="Type",
        description="Set the classification for the RMESH object",
        items = ( ('0', "Mesh", "Mesh"),
                    ('1', "Collision", "Collision"),
                    ('2', "Entity Screen", "Legacy?"),
                    ('3', "Entity Save Screen", "Entity Save Screen"),
                    ('4', "Entity Waypoint", "Entity Waypoint"),
                    ('5', "Entity Light", "Entity Light"),
                    ('6', "Entity Light Fix", "Entity Light Fix"),
                    ('7', "Entity Spotlight", "Legacy?"),
                    ('8', "Entity Sound Emitter", "Entity Sound Emitter"),
                    ('9', "Entity Model", "Legacy?"),
                    ('10', "Entity Mesh", "Entity Mesh")
                )
        )
    
    model_path: StringProperty(
            name = "Model",
            description="Model to use for this entity",
            default="",
            maxlen=1024,
            subtype='DIR_PATH'
    )

    texture_path: StringProperty(
            name = "Texture",
            description="Texture to use for this entity",
            default="",
            maxlen=1024,
            subtype='DIR_PATH'
    )

    sound_emitter_id: IntProperty(
        name = "Sound Emitter ID",
        description = "???"
        )

    has_collision: BoolProperty(
        name ="Has Collision",
        description = "Is the object collidable",
        default = False,
        )

    fx: IntProperty(
        name = "FX",
        description = "???"
        )

def render_screen(context, layout, active_property):
    box = layout.split()
    col = box.column(align=True)
    row = col.row()
    row.label(text='Texture Path:')
    row.prop(active_property, "texture_path", text='')

def render_save_screen(context, layout, active_property):
    box = layout.split()
    col = box.column(align=True)
    row = col.row()
    row.label(text='Model Path:')
    row.prop(active_property, "model_path", text='')
    row = col.row()
    row.label(text='Texture Path:')
    row.prop(active_property, "texture_path", text='')

def render_sound_emitter(context, layout, active_property):
    box = layout.split()
    col = box.column(align=True)
    row = col.row()
    row.label(text='Sound Emitter ID:')
    row.prop(active_property, "sound_emitter_id", text='')

def render_entity_model(context, layout, active_property):
    box = layout.split()
    col = box.column(align=True)
    row = col.row()
    row.label(text='Model Path:')
    row.prop(active_property, "model_path", text='')

def render_entity_mesh(context, layout, active_property):
    box = layout.split()
    col = box.column(align=True)
    row = col.row()
    row.label(text='Model Path:')
    row.prop(active_property, "model_path", text='')
    row = col.row()
    row.label(text='Texture Path:')
    row.prop(active_property, "texture_path", text='')
    row = col.row()
    row.label(text='Has Collision:')
    row.prop(active_property, "has_collision", text='')
    row = col.row()
    row.label(text='FX:')
    row.prop(active_property, "fx", text='')

class RMESH_ObjectProps(Panel):
    bl_label = "Rmesh Object Properties"
    bl_idname = "RMESH_PT_ObjectDetailsPanel"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(self, context):
        valid = False
        ob = context.object

        if hasattr(ob, 'rmesh'):
            valid = True

        return valid

    def draw(self, context):
        layout = self.layout

        ob = context.object
        ob_rmesh = ob.rmesh
        col = layout.column(align=True)
        row = col.row()
        row.label(text='Object Type:')
        row.prop(ob_rmesh, "object_type", text='')
        object_type = ObjectType(int(ob_rmesh.object_type))
        if object_type == ObjectType.entity_screen:
            render_screen(context, layout, ob_rmesh)
        elif object_type == ObjectType.entity_save_screen:
            render_save_screen(context, layout, ob_rmesh)
        elif object_type == ObjectType.entity_sound_emitter:
            render_sound_emitter(context, layout, ob_rmesh)
        elif object_type == ObjectType.entity_model:
            render_entity_model(context, layout, ob_rmesh)
        elif object_type == ObjectType.entity_mesh:
            render_entity_mesh(context, layout, ob_rmesh)

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
    ExportRMESH,
    RMESHObjectPropertiesGroup,
    RMESH_ObjectProps
]

if (4, 1, 0) <= bpy.app.version:
    classesscp.append(ImportRMESH_FileHandler)

def register():
    bpy.utils.register_class(SCPCBAddonPrefs)
    for clsscp in classesscp:
        bpy.utils.register_class(clsscp)

    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.Object.rmesh = PointerProperty(type=RMESHObjectPropertiesGroup, name="RMESH Properties", description="Set properties for your rmesh object")

def unregister():
    bpy.utils.unregister_class(SCPCBAddonPrefs)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    del bpy.types.Object.rmesh
    for clsscp in classesscp:
        bpy.utils.unregister_class(clsscp)

if __name__ == '__main__':
    register()
