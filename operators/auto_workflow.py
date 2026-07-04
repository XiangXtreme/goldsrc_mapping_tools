import bpy
import bmesh
from math import radians
from mathutils import Vector
from bpy.types import Operator
from ..utils import get_prefs



class GOLDSRC_OT_AutoWorkflowAndExport(Operator):
    bl_idname = "goldsrc.auto_workflow_and_export"
    bl_label = "自动工作流并添加到导出列表"
    bl_description = "自动分离面、配置导出设置并将对象添加到导出列表中"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        if bpy.context.object is None:
            self.report({"ERROR"}, "请先选择一个网格物体")
            return {"CANCELLED"}
        
        if bpy.context.object.type != 'MESH':
            self.report({"ERROR"}, "选中的物体不是网格类型")
            return {"CANCELLED"}
        
        # 确保在物体模式
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        original_obj = bpy.context.active_object
        original_name = original_obj.name
        
        # 进入编辑模式
        bpy.context.view_layer.objects.active = original_obj
        bpy.ops.object.mode_set(mode='EDIT')
        
        try:
            # 第一步：分离垂直面（网格体1 - Wall模式）
            perpendicular_count = self.separate_perpendicular_faces(context, original_name)
            
            # 第二步：分离锐角面（网格体2 - Soup-Z模式）
            acute_count = self.separate_acute_faces(context, original_name)
            
            # 第三步：剩余的钝角面保持在原物体（网格体0 - Soup+Z模式）
            self.configure_remaining_obtuse_faces(context, original_obj)
            
            # 返回物体模式
            bpy.ops.object.mode_set(mode='OBJECT')
            
            # 查找所有分离后的对象并添加到导出列表
            world = context.scene.world
            if not world:
                self.report({"ERROR"}, "场景没有世界设置")
                return {'CANCELLED'}
            
            added_objects = []
            
            for obj in bpy.context.scene.objects:
                if obj.type == 'MESH' and any(keyword in obj.name for keyword in ["垂直面", "锐角面", "钝角面"]):
                    # 检查是否已经在列表中
                    exists = False
                    for item in world.qmap_meshes:
                        if item.mesh == obj:
                            exists = True
                            break
                    
                    if not exists:
                        item = world.qmap_meshes.add()
                        item.mesh = obj
                        
                        # 根据对象名称设置导出模式和方向
                        if "垂直面" in obj.name:
                            item.geo_type = 'Prisms'  # 墙壁模式
                        elif "锐角面" in obj.name:
                            item.geo_type = 'Soup'    # 地形模式
                            item.soup_dir = '-Z'      # -Z方向
                        elif "钝角面" in obj.name:
                            item.geo_type = 'Soup'    # 地形模式
                            item.soup_dir = '+Z'      # +Z方向
                        
                        added_objects.append(obj.name)
            
            if added_objects:
                self.report({"INFO"}, f"工作流完成，已添加 {len(added_objects)} 个对象到导出列表。请在世界属性面板中查看并导出。")
            else:
                self.report({"WARNING"}, "工作流完成，但未找到新的分离对象或对象已在导出列表中")
            
            return {"FINISHED"}
            
        except Exception as e:
            self.report({"ERROR"}, f"工作流执行失败: {str(e)}")
            # 确保返回物体模式
            if bpy.context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            return {"CANCELLED"}
    
    def separate_perpendicular_faces(self, context, base_name):
        """分离垂直面并配置为Wall模式"""
        """返回分离的面数量"""
        prefs = get_prefs(context)
        threshold_degrees = prefs.perpendicular_angle_threshold
        threshold_radians = radians(threshold_degrees)
        
        obj = bpy.context.edit_object
        me = obj.data
        bm = bmesh.from_edit_mesh(me)
        
        z_axis = Vector((0, 0, 1))
        perpendicular_angle = radians(90.0)
        
        # 取消所有选择
        for face in bm.faces:
            face.select_set(False)
        
        # 选择垂直面
        selected_count = 0
        for face in bm.faces:
            angle_with_z = face.normal.angle(z_axis)
            if abs(angle_with_z - perpendicular_angle) <= threshold_radians:
                face.select_set(True)
                selected_count += 1
        
        bmesh.update_edit_mesh(me)
        
        if selected_count > 0:
            # 记录分离前的对象和所有现有对象
            original_obj = bpy.context.active_object
            existing_objects = set(bpy.context.scene.objects)
            
            # 分离选中的面
            bpy.ops.mesh.separate(type='SELECTED')
            
            # 返回物体模式来重命名和配置
            bpy.ops.object.mode_set(mode='OBJECT')
            
            # 找到新创建的物体（不在原有对象列表中的）
            new_obj = None
            for obj in bpy.context.scene.objects:
                if obj not in existing_objects and obj.type == 'MESH':
                    new_obj = obj
                    break
            
            if new_obj:
                new_obj.name = f"{base_name}_垂直面_Wall"
                # 配置为Wall模式（Prisms）
                new_obj.qmap_geo_type = 'Prisms'
                
            # 重新进入编辑模式继续处理
            bpy.context.view_layer.objects.active = original_obj
            bpy.ops.object.mode_set(mode='EDIT')
            
        return selected_count
    
    def separate_acute_faces(self, context, base_name):
        """分离锐角面并配置为Soup-Z模式"""
        """返回分离的面数量"""
        obj = bpy.context.edit_object
        me = obj.data
        bm = bmesh.from_edit_mesh(me)
        
        z_axis = Vector((0, 0, 1))
        acute_angle_limit = radians(90.0)
        
        # 取消所有选择
        for face in bm.faces:
            face.select_set(False)
        
        # 选择锐角面
        selected_count = 0
        for face in bm.faces:
            angle_with_z = face.normal.angle(z_axis)
            if angle_with_z < acute_angle_limit - 0.0001:
                face.select_set(True)
                selected_count += 1
        
        bmesh.update_edit_mesh(me)
        
        if selected_count > 0:
            # 记录分离前的对象和所有现有对象
            original_obj = bpy.context.active_object
            existing_objects = set(bpy.context.scene.objects)
            
            # 分离选中的面
            bpy.ops.mesh.separate(type='SELECTED')
            
            # 返回物体模式来重命名和配置
            bpy.ops.object.mode_set(mode='OBJECT')
            
            # 找到新创建的物体（不在原有对象列表中的）
            new_obj = None
            for obj in bpy.context.scene.objects:
                if obj not in existing_objects and obj.type == 'MESH':
                    new_obj = obj
                    break
            
            if new_obj:
                new_obj.name = f"{base_name}_锐角面_Soup-Z"
                # 配置为Soup模式
                new_obj.qmap_geo_type = 'Soup'
                # 设置地形方向为-Z
                new_obj["qmap_soup_dir"] = '-Z'
                
            # 重新进入编辑模式继续处理
            bpy.context.view_layer.objects.active = original_obj
            bpy.ops.object.mode_set(mode='EDIT')
            
        return selected_count
    
    def configure_remaining_obtuse_faces(self, context, original_obj):
        """配置剩余的钝角面为Soup+Z模式"""
        # 返回物体模式来配置原物体
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # 重命名原物体
        base_name = original_obj.name.split('_')[0]  # 获取基础名称
        original_obj.name = f"{base_name}_钝角面_Soup+Z"
        
        # 配置为Soup模式，+Z方向
        original_obj.qmap_geo_type = 'Soup'
        original_obj["qmap_soup_dir"] = '+Z'