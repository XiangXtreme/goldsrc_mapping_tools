import bpy
import bmesh
from bpy.props import StringProperty, BoolProperty
from bpy_extras.io_utils import ImportHelper
import struct
import os
from mathutils import Vector


class WADImportError(Exception):
    """WAD导入相关的异常"""
    pass


class WAD3Loader:
    """WAD3文件加载器，基于HL-Texture-Tools的实现"""
    
    def __init__(self):
        self.lumps_info = []
        self.filename = ""
        self.file_handle = None
        
        # 常量定义
        self.MAX_PALETTE_COLORS = 256
        self.MAX_NAME_LENGTH = 16
        self.LUMP_SIZE = 32
        self.MAX_TEXTURE_WIDTH = 4096
        self.MAX_TEXTURE_HEIGHT = 4096
        self.WAD_HEADER_ID = b'WAD3'
        
    def load_file(self, filepath):
        """加载WAD3文件"""
        self.filename = filepath
        self.lumps_info.clear()
        
        try:
            self.file_handle = open(filepath, 'rb')
            
            # 读取文件头
            header_id = self.file_handle.read(4)
            if header_id != self.WAD_HEADER_ID:
                raise WADImportError(f"无效的WAD文件: {filepath}")
                
            lump_count = struct.unpack('<I', self.file_handle.read(4))[0]
            lump_offset = struct.unpack('<I', self.file_handle.read(4))[0]
            
            # 加载所有lump信息
            self._load_lumps_info(lump_count, lump_offset)
            
        except Exception as e:
            self.close()
            raise WADImportError(f"加载WAD文件失败: {str(e)}")
    
    def _load_lumps_info(self, lump_count, lump_offset):
        """加载lump信息"""
        self.file_handle.seek(lump_offset)
        
        for i in range(lump_count):
            offset = struct.unpack('<I', self.file_handle.read(4))[0]
            compressed_length = struct.unpack('<I', self.file_handle.read(4))[0]
            full_length = struct.unpack('<I', self.file_handle.read(4))[0]
            lump_type = struct.unpack('<B', self.file_handle.read(1))[0]
            compression = struct.unpack('<B', self.file_handle.read(1))[0]
            
            # 跳过2字节填充
            self.file_handle.seek(2, 1)
            
            # 读取名称
            name_bytes = self.file_handle.read(self.MAX_NAME_LENGTH)
            name = name_bytes.split(b'\x00')[0].decode('ascii', errors='ignore')
            
            lump_info = {
                'offset': offset,
                'compressed_length': compressed_length,
                'full_length': full_length,
                'type': lump_type,
                'compression': compression,
                'name': name
            }
            
            self.lumps_info.append(lump_info)
    
    def get_lump_image_data(self, index):
        """获取lump的图像数据"""
        if index < 0 or index >= len(self.lumps_info):
            raise WADImportError(f"无效的lump索引: {index}")
            
        lump = self.lumps_info[index]
        lump_type = lump['type']
        
        # 支持的类型: 0x40 (tempdecal), 0x42 (cached), 0x43 (normal), 0x46 (fonts)
        if lump_type not in [0x40, 0x42, 0x43, 0x46]:
            raise WADImportError(f"不支持的lump类型: 0x{lump_type:02X}")
            
        self.file_handle.seek(lump['offset'])
        
        # 跳过lump名称（对于某些类型）
        if lump_type in [0x40, 0x43]:
            self.file_handle.seek(self.MAX_NAME_LENGTH, 1)
            
        # 读取纹理尺寸
        width = struct.unpack('<I', self.file_handle.read(4))[0]
        height = struct.unpack('<I', self.file_handle.read(4))[0]
        
        if width > self.MAX_TEXTURE_WIDTH or height > self.MAX_TEXTURE_HEIGHT:
            raise WADImportError(f"纹理尺寸超出限制: {width}x{height}")
            
        if width == 0 or height == 0:
            raise WADImportError("纹理尺寸必须大于0")
            
        # 跳过像素偏移和mipmap偏移（对于某些类型）
        if lump_type in [0x40, 0x43]:
            self.file_handle.seek(16, 1)  # 4字节像素偏移 + 12字节mipmap偏移
            
        # 读取像素数据
        pixel_size = width * height
        pixels = self.file_handle.read(pixel_size)
        
        # 跳过mipmap数据（如果存在）
        if lump_type in [0x40, 0x43]:
            mipmap1_size = (width // 2) * (height // 2)
            mipmap2_size = (width // 4) * (height // 4)
            mipmap3_size = (width // 8) * (height // 8)
            self.file_handle.seek(mipmap1_size + mipmap2_size + mipmap3_size, 1)
            
        # 跳过2字节填充
        self.file_handle.seek(2, 1)
        
        # 读取调色板
        palette_data = self.file_handle.read(self.MAX_PALETTE_COLORS * 3)
        palette = []
        for i in range(0, len(palette_data), 3):
            if i + 2 < len(palette_data):
                r, g, b = palette_data[i], palette_data[i+1], palette_data[i+2]
                palette.append((r/255.0, g/255.0, b/255.0, 1.0))
        
        return {
            'name': lump['name'],
            'width': width,
            'height': height,
            'pixels': pixels,
            'palette': palette
        }
    
    def close(self):
        """关闭文件句柄"""
        if self.file_handle:
            self.file_handle.close()
            self.file_handle = None


class GOLDSRC_OT_ImportWAD(bpy.types.Operator, ImportHelper):
    """导入WAD纹理文件"""
    bl_idname = "goldsrc.import_wad"
    bl_label = "导入WAD纹理"
    bl_description = "从WAD文件导入纹理"
    bl_options = {'REGISTER', 'UNDO'}
    
    # 文件过滤器
    filename_ext = ".wad"
    filter_glob: StringProperty(
        default="*.wad",
        options={'HIDDEN'},
        maxlen=255,
    )
    
    # 导入选项
    import_as_materials: BoolProperty(
        name="创建材质",
        description="为每个纹理创建Blender材质",
        default=True,
    )
    
    create_preview_planes: BoolProperty(
        name="创建预览平面",
        description="为每个纹理创建预览平面",
        default=False,
    )
    
    def execute(self, context):
        try:
            # 加载WAD文件
            wad_loader = WAD3Loader()
            wad_loader.load_file(self.filepath)
            
            imported_count = 0
            
            for i, lump in enumerate(wad_loader.lumps_info):
                try:
                    # 获取图像数据
                    image_data = wad_loader.get_lump_image_data(i)
                    
                    # 创建Blender图像
                    image = self._create_blender_image(image_data)
                    
                    if self.import_as_materials:
                        self._create_material(image, image_data['name'])
                        
                    if self.create_preview_planes:
                        self._create_preview_plane(image, image_data, i)
                        
                    imported_count += 1
                    
                except Exception as e:
                    self.report({'WARNING'}, f"跳过纹理 {lump['name']}: {str(e)}")
                    continue
            
            wad_loader.close()
            
            self.report({'INFO'}, f"成功导入 {imported_count} 个纹理")
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"导入WAD文件失败: {str(e)}")
            return {'CANCELLED'}
    
    def _create_blender_image(self, image_data):
        """创建Blender图像"""
        name = image_data['name']
        width = image_data['width']
        height = image_data['height']
        pixels = image_data['pixels']
        palette = image_data['palette']
        
        # 创建图像
        image = bpy.data.images.new(name, width, height)
        
        # 转换索引像素为RGBA
        rgba_pixels = []
        for pixel_index in pixels:
            if pixel_index < len(palette):
                rgba_pixels.extend(palette[pixel_index])
            else:
                rgba_pixels.extend([0.0, 0.0, 0.0, 1.0])  # 黑色作为默认
        
        # 设置像素数据
        image.pixels = rgba_pixels
        image.pack()
        
        return image
    
    def _create_material(self, image, name):
        """创建材质"""
        material = bpy.data.materials.new(name=f"{name}")
        material.use_nodes = True
        
        # 清除默认节点
        material.node_tree.nodes.clear()
        
        # 创建节点
        output_node = material.node_tree.nodes.new('ShaderNodeOutputMaterial')
        bsdf_node = material.node_tree.nodes.new('ShaderNodeBsdfPrincipled')
        tex_node = material.node_tree.nodes.new('ShaderNodeTexImage')
        
        # 设置纹理
        tex_node.image = image
        
        # 连接节点
        material.node_tree.links.new(tex_node.outputs['Color'], bsdf_node.inputs['Base Color'])
        material.node_tree.links.new(bsdf_node.outputs['BSDF'], output_node.inputs['Surface'])
        
        # 处理透明纹理（以{开头的纹理名）
        if name.startswith('{'):
            material.node_tree.links.new(tex_node.outputs['Alpha'], bsdf_node.inputs['Alpha'])
            material.blend_method = 'BLEND'
        
        return material
    
    def _create_preview_plane(self, image, image_data, index):
        """创建预览平面"""
        name = image_data['name']
        width = image_data['width']
        height = image_data['height']
        
        # 创建网格
        bpy.ops.mesh.primitive_plane_add()
        plane = bpy.context.active_object
        plane.name = f"PLANE_{name}"
        
        # 调整尺寸（保持纵横比）
        scale_factor = max(width, height) / 256.0  # 标准化到合理尺寸
        plane.scale = (width / max(width, height) * scale_factor, 
                      height / max(width, height) * scale_factor, 
                      1.0)
        
        # 设置位置（网格排列）
        grid_size = 10
        x_offset = (index % grid_size) * 3
        y_offset = (index // grid_size) * 3
        plane.location = (x_offset, y_offset, 0)
        
        # 应用材质
        if self.import_as_materials:
            material_name = f"MAT_{name}"
            if material_name in bpy.data.materials:
                plane.data.materials.append(bpy.data.materials[material_name])


def menu_func_import(self, context):
    self.layout.operator(
        GOLDSRC_OT_ImportWAD.bl_idname, text="WAD纹理 (.wad)"
    )


def register():
    bpy.utils.register_class(GOLDSRC_OT_ImportWAD)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.utils.unregister_class(GOLDSRC_OT_ImportWAD)


if __name__ == "__main__":
    register()