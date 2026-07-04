import bpy
import bmesh
from math import radians, degrees
from mathutils import Vector, geometry
from bpy.types import Operator
from ..utils import get_prefs


class GOLDSRC_OT_BlobSeparation(Operator):
    bl_idname = "goldsrc.blob_separation"
    bl_label = "Blob模式智能分离"
    bl_description = "将网格体智能分离为多个子网格，每个子网格适合使用Blob模式导出"
    bl_options = {"REGISTER", "UNDO"}
    
    # 分离参数
    max_angle_threshold: bpy.props.FloatProperty(
        name="最大角度阈值",
        description="面法线之间的最大角度差异（度）",
        default=45.0,
        min=10.0,
        max=90.0
    )
    
    min_faces_per_group: bpy.props.IntProperty(
        name="最小面数",
        description="每个分离组的最小面数",
        default=3,
        min=1,
        max=50
    )
    
    use_convexity_check: bpy.props.BoolProperty(
        name="凸性检查",
        description="检查分离后的网格是否适合blob模式（凸性检查）",
        default=True
    )

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
        
        try:
            # 分析网格并进行智能分离
            separated_objects = self.intelligent_blob_separation(context, original_obj)
            
            if not separated_objects:
                self.report({"WARNING"}, "未能分离出适合blob模式的子网格")
                return {"FINISHED"}
            
            # 添加到导出列表
            self.add_to_export_list(context, separated_objects)
            
            self.report({"INFO"}, f"成功分离出 {len(separated_objects)} 个适合blob模式的子网格")
            return {"FINISHED"}
            
        except Exception as e:
            self.report({"ERROR"}, f"Blob分离失败: {str(e)}")
            return {"CANCELLED"}
    
    def intelligent_blob_separation(self, context, original_obj):
        """智能分离网格为适合blob模式的子网格"""
        # 复制原始对象
        bpy.context.view_layer.objects.active = original_obj
        bpy.ops.object.duplicate()
        work_obj = bpy.context.active_object
        work_obj.name = f"{original_obj.name}_blob_work"
        
        # 进入编辑模式
        bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(work_obj.data)
        
        # 分析面的连通性和法线方向
        face_groups = self.analyze_face_connectivity(bm)
        
        # 过滤掉太小的组
        valid_groups = [group for group in face_groups if len(group) >= self.min_faces_per_group]
        
        if not valid_groups:
            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.data.objects.remove(work_obj)
            return []
        
        # 进一步优化分组，确保每组都适合blob模式
        optimized_groups = self.optimize_groups_for_blob(bm, valid_groups)
        
        separated_objects = []
        
        # 为每个优化后的组创建单独的对象
        for i, face_group in enumerate(optimized_groups):
            # 选择当前组的面
            bpy.ops.mesh.select_all(action='DESELECT')
            for face_idx in face_group:
                if face_idx < len(bm.faces):
                    bm.faces[face_idx].select = True
            
            bmesh.update_edit_mesh(work_obj.data)
            
            # 分离选中的面
            bpy.ops.mesh.separate(type='SELECTED')
        
        # 退出编辑模式
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # 收集分离后的对象
        for obj in bpy.context.scene.objects:
            if obj.type == 'MESH' and obj.name.startswith(f"{original_obj.name}_blob_work"):
                # 重命名对象
                group_idx = len(separated_objects)
                obj.name = f"{original_obj.name}_blob_{group_idx:02d}"
                
                # 为每个对象找到最佳原点位置
                optimal_origin = self.find_optimal_blob_origin(obj)
                if optimal_origin:
                    # 设置对象原点到最佳位置
                    self.set_object_origin(obj, optimal_origin)
                
                # 进行最终的blob适用性检查
                if self.use_convexity_check and not self.check_blob_suitability_advanced(obj):
                    self.report({"WARNING"}, f"对象 {obj.name} 可能不适合blob模式（存在面穿透问题）")
                
                separated_objects.append(obj)
        
        return separated_objects
    
    def analyze_face_connectivity(self, bm):
        """分析面的连通性，基于法线相似性进行分组"""
        if not bm.faces:
            return []
        
        # 确保面索引是最新的
        bm.faces.ensure_lookup_table()
        
        visited = set()
        face_groups = []
        angle_threshold = radians(self.max_angle_threshold)
        
        for face in bm.faces:
            if face.index in visited:
                continue
            
            # 开始新的连通组
            current_group = []
            stack = [face]
            
            while stack:
                current_face = stack.pop()
                if current_face.index in visited:
                    continue
                
                visited.add(current_face.index)
                current_group.append(current_face.index)
                
                # 检查相邻面
                for edge in current_face.edges:
                    for linked_face in edge.link_faces:
                        if linked_face.index not in visited:
                            # 检查法线角度差异
                            angle_diff = current_face.normal.angle(linked_face.normal)
                            if angle_diff <= angle_threshold:
                                stack.append(linked_face)
            
            if current_group:
                face_groups.append(current_group)
        
        return face_groups
    
    def optimize_groups_for_blob(self, bm, face_groups):
        """优化面组，确保每组都适合blob模式"""
        optimized_groups = []
        
        for group in face_groups:
            # 检查当前组是否需要进一步分割
            sub_groups = self.split_group_by_visibility(bm, group)
            optimized_groups.extend(sub_groups)
        
        return optimized_groups
    
    def split_group_by_visibility(self, bm, face_indices):
        """根据可见性分割面组，避免面穿透问题"""
        if len(face_indices) < self.min_faces_per_group:
            return [face_indices]
        
        # 尝试不同的分割策略
        best_split = self.find_best_split_strategy(bm, face_indices)
        
        if best_split and len(best_split) > 1:
            # 递归处理每个子组
            result = []
            for sub_group in best_split:
                if len(sub_group) >= self.min_faces_per_group:
                    result.extend(self.split_group_by_visibility(bm, sub_group))
            return result if result else [face_indices]
        
        return [face_indices]
    
    def find_best_split_strategy(self, bm, face_indices):
        """寻找最佳的面组分割策略"""
        if len(face_indices) < 6:  # 太小的组不分割
            return None
        
        # 计算面组的几何中心
        face_centers = []
        for face_idx in face_indices:
            if face_idx < len(bm.faces):
                face = bm.faces[face_idx]
                center = sum([v.co for v in face.verts], Vector()) / len(face.verts)
                face_centers.append((face_idx, center))
        
        if len(face_centers) < 6:
            return None
        
        # 基于空间位置进行K-means聚类分割
        return self.kmeans_split_faces(face_centers, 2)
    
    def kmeans_split_faces(self, face_centers, k=2):
        """使用简化的K-means算法分割面"""
        if len(face_centers) < k * 2:
            return None
        
        # 初始化聚类中心
        import random
        random.seed(42)  # 确保结果可重现
        
        centers = random.sample(face_centers, k)
        cluster_centers = [fc[1] for fc in centers]
        
        # 迭代优化
        for _ in range(10):  # 最多10次迭代
            clusters = [[] for _ in range(k)]
            
            # 分配面到最近的聚类中心
            for face_idx, face_center in face_centers:
                distances = [(face_center - cc).length for cc in cluster_centers]
                closest_cluster = distances.index(min(distances))
                clusters[closest_cluster].append(face_idx)
            
            # 更新聚类中心
            new_centers = []
            for i, cluster in enumerate(clusters):
                if cluster:
                    cluster_positions = [fc[1] for fc in face_centers if fc[0] in cluster]
                    new_center = sum(cluster_positions, Vector()) / len(cluster_positions)
                    new_centers.append(new_center)
                else:
                    new_centers.append(cluster_centers[i])
            
            cluster_centers = new_centers
        
        # 返回非空的聚类
        return [cluster for cluster in clusters if len(cluster) >= self.min_faces_per_group]
    
    def find_optimal_blob_origin(self, obj):
        """为对象找到最佳的blob原点位置"""
        mesh = obj.data
        vertices = [obj.matrix_world @ v.co for v in mesh.vertices]
        
        if not vertices:
            return None
        
        # 尝试多个候选原点位置
        candidates = []
        
        # 1. 几何中心
        geometric_center = sum(vertices, Vector()) / len(vertices)
        candidates.append(geometric_center)
        
        # 2. 包围盒中心
        min_co = Vector((min(v.x for v in vertices), min(v.y for v in vertices), min(v.z for v in vertices)))
        max_co = Vector((max(v.x for v in vertices), max(v.y for v in vertices), max(v.z for v in vertices)))
        bbox_center = (min_co + max_co) / 2
        candidates.append(bbox_center)
        
        # 3. 体积加权中心（近似）
        volume_center = self.calculate_volume_weighted_center(obj)
        if volume_center:
            candidates.append(volume_center)
        
        # 评估每个候选位置
        best_origin = None
        best_score = -1
        
        for candidate in candidates:
            score = self.evaluate_blob_origin(obj, candidate)
            if score > best_score:
                best_score = score
                best_origin = candidate
        
        return best_origin if best_score > 0.5 else None
    
    def calculate_volume_weighted_center(self, obj):
        """计算体积加权中心（近似）"""
        mesh = obj.data
        if len(mesh.polygons) < 4:
            return None
        
        # 简化计算：使用三角形面积加权
        weighted_center = Vector()
        total_area = 0
        
        for poly in mesh.polygons:
            if len(poly.vertices) >= 3:
                # 计算面的中心和面积
                face_verts = [obj.matrix_world @ mesh.vertices[v].co for v in poly.vertices]
                face_center = sum(face_verts, Vector()) / len(face_verts)
                
                # 简化面积计算（对于三角形）
                if len(face_verts) >= 3:
                    area = ((face_verts[1] - face_verts[0]).cross(face_verts[2] - face_verts[0])).length / 2
                    weighted_center += face_center * area
                    total_area += area
        
        return weighted_center / total_area if total_area > 0 else None
    
    def evaluate_blob_origin(self, obj, origin):
        """评估原点位置的适用性"""
        mesh = obj.data
        vertices = [obj.matrix_world @ v.co for v in mesh.vertices]
        
        if not vertices:
            return 0
        
        # 检查从原点到所有面的射线是否穿透其他面
        penetration_count = 0
        total_faces = len(mesh.polygons)
        
        for poly in mesh.polygons:
            # 计算面中心
            face_verts = [vertices[v] for v in poly.vertices]
            face_center = sum(face_verts, Vector()) / len(face_verts)
            
            # 从原点到面中心的射线
            ray_direction = (face_center - origin).normalized()
            ray_length = (face_center - origin).length
            
            # 检查射线是否与其他面相交
            if self.ray_intersects_other_faces(origin, ray_direction, ray_length, mesh, poly.index, obj.matrix_world):
                penetration_count += 1
        
        # 计算适用性评分（穿透面越少越好）
        penetration_ratio = penetration_count / total_faces
        return max(0, 1.0 - penetration_ratio * 2)  # 穿透率超过50%就不适用
    
    def ray_intersects_other_faces(self, ray_origin, ray_direction, ray_length, mesh, exclude_face_idx, matrix_world):
        """检查射线是否与其他面相交"""
        for i, poly in enumerate(mesh.polygons):
            if i == exclude_face_idx:
                continue
            
            # 获取面的顶点
            face_verts = [matrix_world @ mesh.vertices[v].co for v in poly.vertices]
            
            if len(face_verts) >= 3:
                # 简化：只检查与三角形的相交
                for j in range(1, len(face_verts) - 1):
                    triangle = [face_verts[0], face_verts[j], face_verts[j + 1]]
                    
                    # 射线-三角形相交测试
                    intersection = geometry.intersect_ray_tri(
                        triangle[0], triangle[1], triangle[2],
                        ray_direction, ray_origin
                    )
                    
                    if intersection and (intersection - ray_origin).length < ray_length * 0.95:
                        return True
        
        return False
    
    def set_object_origin(self, obj, new_origin):
        """设置对象的原点到指定位置"""
        # 保存当前选择
        old_active = bpy.context.view_layer.objects.active
        old_selected = bpy.context.selected_objects[:]
        
        # 选择目标对象
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        
        # 设置3D游标到新原点位置
        bpy.context.scene.cursor.location = new_origin
        
        # 设置原点到3D游标
        bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
        
        # 恢复选择
        bpy.ops.object.select_all(action='DESELECT')
        for o in old_selected:
            if o and o.name in bpy.data.objects:
                o.select_set(True)
        if old_active and old_active.name in bpy.data.objects:
            bpy.context.view_layer.objects.active = old_active
    
    def check_blob_suitability_advanced(self, obj):
        """高级blob适用性检查，考虑面穿透问题"""
        # 使用当前对象的原点进行检查
        origin = obj.matrix_world @ Vector((0, 0, 0))
        score = self.evaluate_blob_origin(obj, origin)
        
        return score > 0.7  # 要求较高的适用性评分
    
    def check_blob_suitability(self, obj):
        """检查对象是否适合blob模式（简单的凸性检查）"""
        # 获取网格数据
        mesh = obj.data
        
        # 计算几何中心
        vertices = [obj.matrix_world @ v.co for v in mesh.vertices]
        if not vertices:
            return False
        
        center = sum(vertices, Vector()) / len(vertices)
        
        # 检查所有面是否都"面向外部"
        for poly in mesh.polygons:
            face_center = sum([vertices[v] for v in poly.vertices], Vector()) / len(poly.vertices)
            face_normal = poly.normal.copy()
            face_normal.rotate(obj.matrix_world)
            
            # 从几何中心到面中心的向量
            center_to_face = (face_center - center).normalized()
            
            # 如果法线与中心到面的向量夹角大于90度，可能是内凹的
            if face_normal.dot(center_to_face) < 0:
                return False
        
        return True
    
    def add_to_export_list(self, context, objects):
        """将分离的对象添加到导出列表"""
        world = context.scene.world
        if not world:
            return
        
        for obj in objects:
            # 检查是否已经在列表中
            exists = False
            for item in world.qmap_meshes:
                if item.mesh == obj:
                    exists = True
                    break
            
            if not exists:
                item = world.qmap_meshes.add()
                item.mesh = obj
                item.geo_type = 'Blob'  # 设置为Blob模式


class GOLDSRC_OT_AnalyzeBlobSuitability(Operator):
    bl_idname = "goldsrc.analyze_blob_suitability"
    bl_label = "分析Blob适用性"
    bl_description = "分析选中的网格是否适合使用Blob模式导出"
    bl_options = {"REGISTER"}
    
    def execute(self, context):
        if bpy.context.object is None or bpy.context.object.type != 'MESH':
            self.report({"ERROR"}, "请选择一个网格物体")
            return {"CANCELLED"}
        
        obj = bpy.context.active_object
        
        # 分析网格特征
        analysis_result = self.analyze_mesh_for_blob(obj)
        
        # 报告分析结果
        if analysis_result['suitable']:
            self.report({"INFO"}, f"网格适合Blob模式。凸性评分: {analysis_result['convexity_score']:.2f}")
        else:
            reasons = ", ".join(analysis_result['issues'])
            self.report({"WARNING"}, f"网格可能不适合Blob模式。问题: {reasons}")
        
        return {"FINISHED"}
    
    def analyze_mesh_for_blob(self, obj):
        """分析网格是否适合blob模式"""
        mesh = obj.data
        result = {
            'suitable': True,
            'convexity_score': 1.0,
            'issues': []
        }
        
        if len(mesh.polygons) < 4:
            result['suitable'] = False
            result['issues'].append("面数太少")
            return result
        
        # 计算几何中心
        vertices = [obj.matrix_world @ v.co for v in mesh.vertices]
        center = sum(vertices, Vector()) / len(vertices)
        
        # 检查凸性
        inward_faces = 0
        total_faces = len(mesh.polygons)
        
        for poly in mesh.polygons:
            face_center = sum([vertices[v] for v in poly.vertices], Vector()) / len(poly.vertices)
            face_normal = poly.normal.copy()
            face_normal.rotate(obj.matrix_world)
            
            center_to_face = (face_center - center).normalized()
            
            if face_normal.dot(center_to_face) < 0.1:  # 容忍度
                inward_faces += 1
        
        convexity_score = 1.0 - (inward_faces / total_faces)
        result['convexity_score'] = convexity_score
        
        if convexity_score < 0.8:
            result['suitable'] = False
            result['issues'].append(f"凸性不足 ({convexity_score:.2f})")
        
        if inward_faces > total_faces * 0.3:
            result['issues'].append(f"过多内向面 ({inward_faces}/{total_faces})")
        
        return result