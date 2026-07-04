bl_info = {
    "name": "Goldsrc Mapping Tools",
    "author": "Lws",
    "version": (0, 2, 0),
    "blender": (3, 0, 0),
    "location": "File > Import / 3D View > N Panel",
    "description": "Lws's goldsrc mapping tools - 模块化版本",
    "warning": "",
    "category": "Import-Export",
}

import bpy
from . import export_map, preferences, panels
from .operators import (
    GOLDSRC_OT_ImportFromFile,
    GOLDSRC_OT_ImportFromClipboard,
    GOLDSRC_OT_SelectAcuteFaces,
    GOLDSRC_OT_SelectObtuseFaces,
    GOLDSRC_OT_SelectPerpendicularFaces,
    GOLDSRC_OT_AutoWorkflowAndExport,
    GOLDSRC_OT_ImportWAD,
    GOLDSRC_OT_UnwrapSelectedQuadStrip,
)


def menu_func_import(self, context):
    self.layout.operator(
        GOLDSRC_OT_ImportFromFile.bl_idname, text="MAP (.map) via Goldsrc Mapping Tools"
    )


classes = (
    preferences.GOLDSRC_AddonPreferences,
    GOLDSRC_OT_ImportFromFile,
    GOLDSRC_OT_ImportFromClipboard,
    GOLDSRC_OT_SelectAcuteFaces,
    GOLDSRC_OT_SelectObtuseFaces,
    GOLDSRC_OT_SelectPerpendicularFaces,
    GOLDSRC_OT_AutoWorkflowAndExport,
    GOLDSRC_OT_ImportWAD,
    GOLDSRC_OT_UnwrapSelectedQuadStrip,
    panels.GOLDSRC_PT_Tools,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    export_map.register()


def unregister():
    export_map.unregister()
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
