import bpy
from bpy.types import Panel
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


class GOLDSRC_PT_Tools(Panel):
    bl_label = "Goldsrc Mapping Tools"
    bl_idname = "GOLDSRC_MAPPING_TOOLS_PT_Tools"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Goldsrc"

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        
        # 导入功能
        col.label(text="导入工具:")
        import_col = col.column(align=True)
        import_col.operator(GOLDSRC_OT_ImportFromFile.bl_idname, text="直接导入MAP", icon="IMPORT")
        import_col.operator(GOLDSRC_OT_ImportFromClipboard.bl_idname, text="剪贴板MAP直导", icon="PASTEDOWN")
        import_col.operator(GOLDSRC_OT_ImportWAD.bl_idname, text="导入WAD纹理", icon="TEXTURE")
        col.separator()
        
        # 自动工作流
        col.label(text="自动工作流:")
        workflow_col = col.column(align=True)
        workflow_col.operator(GOLDSRC_OT_AutoWorkflowAndExport.bl_idname, text="自动工作流+添加到导出列表", icon="PLUS")

        col.separator()
        col.label(text="导出工具:")
        export_col = col.column(align=True)
        export_col.operator("qmap.add_selected_meshes", text="添加选中网格到导出列表", icon="PLUS")
        export_col.operator("qmap.export_world_map", text="导出MAP", icon="EXPORT")
        
        col.separator()
        
        # 面选择功能
        col.label(text="面选择工具:")
        face_col = col.column(align=True)
        face_col.operator(GOLDSRC_OT_SelectAcuteFaces.bl_idname, text="选择锐角面", icon="FACESEL")
        face_col.operator(GOLDSRC_OT_SelectObtuseFaces.bl_idname, text="选择钝角面", icon="FACESEL")
        face_col.operator(GOLDSRC_OT_SelectPerpendicularFaces.bl_idname, text="选择垂直面", icon="FACESEL")
        face_col.operator(GOLDSRC_OT_UnwrapSelectedQuadStrip.bl_idname, text="选中四边面曲线UV", icon="UV")
        
        col.separator()
        col.operator("preferences.addon_show", text="打开插件首选项").module = __name__.split('.')[0]
