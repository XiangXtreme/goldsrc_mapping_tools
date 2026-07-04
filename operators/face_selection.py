import bpy
import bmesh
from math import radians
from mathutils import Vector
from bpy.types import Operator
from ..utils import get_prefs


class GOLDSRC_OT_SelectAcuteFaces(Operator):
    bl_idname = "goldsrc.select_acute_faces"
    bl_label = "选择锐角面"
    bl_description = "选择与+Z轴夹角为锐角的面"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        if bpy.context.object is None or bpy.context.object.mode != 'EDIT':
            self.report({"ERROR"}, "请先选择物体并进入编辑模式")
            return {"CANCELLED"}
        
        obj = bpy.context.edit_object
        me = obj.data
        bm = bmesh.from_edit_mesh(me)
        
        z_axis = Vector((0, 0, 1))
        acute_angle_limit = radians(90.0)
        
        selected_count = 0
        for face in bm.faces:
            angle_with_z = face.normal.angle(z_axis)
            if angle_with_z < acute_angle_limit - 0.0001:
                face.select_set(True)
                selected_count += 1
            else:
                face.select_set(False)
        
        bmesh.update_edit_mesh(me)
        self.report({"INFO"}, f"已选择 {selected_count} 个锐角面")
        return {"FINISHED"}


class GOLDSRC_OT_SelectObtuseFaces(Operator):
    bl_idname = "goldsrc.select_obtuse_faces"
    bl_label = "选择钝角面"
    bl_description = "选择与+Z轴夹角为钝角的面"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        if bpy.context.object is None or bpy.context.object.mode != 'EDIT':
            self.report({"ERROR"}, "请先选择物体并进入编辑模式")
            return {"CANCELLED"}
        
        obj = bpy.context.edit_object
        me = obj.data
        bm = bmesh.from_edit_mesh(me)
        
        z_axis = Vector((0, 0, 1))
        acute_angle_limit = radians(90.0)
        
        selected_count = 0
        for face in bm.faces:
            angle_with_z = face.normal.angle(z_axis)
            if angle_with_z > acute_angle_limit + 0.0001:
                face.select_set(True)
                selected_count += 1
            else:
                face.select_set(False)
        
        bmesh.update_edit_mesh(me)
        self.report({"INFO"}, f"已选择 {selected_count} 个钝角面")
        return {"FINISHED"}


class GOLDSRC_OT_SelectPerpendicularFaces(Operator):
    bl_idname = "goldsrc.select_perpendicular_faces"
    bl_label = "选择垂直面"
    bl_description = "选择与+Z轴垂直的面（与XY平面平行）"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        if bpy.context.object is None or bpy.context.object.mode != 'EDIT':
            self.report({"ERROR"}, "请先选择物体并进入编辑模式")
            return {"CANCELLED"}
        
        prefs = get_prefs(context)
        threshold_degrees = prefs.perpendicular_angle_threshold
        threshold_radians = radians(threshold_degrees)
        
        obj = bpy.context.edit_object
        me = obj.data
        bm = bmesh.from_edit_mesh(me)
        
        z_axis = Vector((0, 0, 1))
        perpendicular_angle = radians(90.0)
        
        selected_count = 0
        for face in bm.faces:
            angle_with_z = face.normal.angle(z_axis)
            # 检查是否接近90度（垂直于Z轴）
            if abs(angle_with_z - perpendicular_angle) <= threshold_radians:
                face.select_set(True)
                selected_count += 1
            else:
                face.select_set(False)
        
        bmesh.update_edit_mesh(me)
        self.report({"INFO"}, f"已选择 {selected_count} 个垂直面（阈值: {threshold_degrees}°）")
        return {"FINISHED"}