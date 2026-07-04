# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# ##### END GPL LICENSE BLOCK #####

bl_info = {
    "name": "Export Quake Map (.map)",
    "author": "chedap",
    "version": (2024, 1, 22),
    "blender": (4, 0, 2),
    "location": "File > Import-Export",
    "description": "Export scene to idTech map format",
    "category": "Import-Export",
    "doc_url": "https://github.com/c-d-a/io_export_qmap",
}

import bpy, bmesh, math, time
from collections import defaultdict
from mathutils import Vector, Matrix, Euler, geometry
from numpy.linalg import solve
from numpy import format_float_positional as fformat
from bpy_extras.io_utils import ExportHelper
from bpy.props import *

# clipboard stuff
import sys, struct, ctypes

if sys.platform.startswith("win"):
    from ctypes import wintypes as w32

    k32 = ctypes.windll.kernel32
    u32 = ctypes.windll.user32
    k32.GlobalAlloc.argtypes = w32.UINT, ctypes.c_size_t
    k32.GlobalAlloc.restype = w32.HGLOBAL
    k32.GlobalLock.argtypes = (w32.HGLOBAL,)
    k32.GlobalLock.restype = w32.LPVOID
    k32.GlobalUnlock.argtypes = (w32.HGLOBAL,)
    k32.RtlCopyMemory.argtypes = w32.LPVOID, w32.LPCVOID, ctypes.c_size_t
    u32.OpenClipboard.argtypes = (w32.HWND,)
    u32.SetClipboardData.argtypes = w32.UINT, w32.HANDLE

ptxt = {
    "sel": {"name": "仅选中项", "def": True, "desc": "只导出选中的对象"},
    "tm": {"name": "应用变换", "def": True, "desc": "应用当前的旋转、平移和缩放"},
    "mod": {
        "name": "应用修改器",
        "def": True,
        "desc": "导出前应用修改器，使用它们的视图设置",
    },
    "tj": {
        "name": "三角化180°",
        "def": True,
        "desc": "拆分带有中边顶点的面（以获得更好的UV）",
    },
    "geo": {
        "name": "网格",
        "def": "Faces",
        "items": (
            (
                "Brush",
                "笔刷(Brush)",
                "将每个网格导出为单个笔刷"
                "\n\n更多控制，但需要更多准备工作"
                "\n默认情况下，笔刷按集合分组",
            ),
            (
                "Faces",
                "面(Faces)",
                "将每个面导出为金字塔笔刷" "\n\n最适合详细几何体，但之后难以编辑",
            ),
            (
                "Prisms",
                "墙壁(Walls)",
                "将每个面导出为挤压棱柱笔刷" "\n\n最适合您计划之后编辑的简单墙壁",
            ),
            (
                "Soup",
                "地形(Terrain)",
                "将面导出为垂直挤压的多边形组"
                "\n\n沿Z轴将面挤压到其最低顶点的高度"
                "\n当您想节省碰撞平面时很有用",
            ),
            (
                "Blob",
                "球体(Blob)",
                "将面导出为具有共同顶点的金字塔"
                "\n\n将共享顶点放在网格的几何中心"
                "\n当您想要一个实心密封的凸状岩石时很有用",
            ),
            (
                "Miter",
                "外壳(Shell)",
                "将面导出为实体化外壳"
                "\n\n沿顶点法线挤压，中间有斜接接头"
                "\n不可靠，因为生成的接头可能不是平面的",
            ),
            (
                "ArrayPrisms",
                "阵列棱柱(Array Prisms)",
                "将连续截面阵列导出为多个棱柱笔刷"
                "\n\n适合由合法三棱柱、方柱或其他凸截面沿曲线/阵列生成的结构",
            ),
            ("Patches", "补丁", "将每个面导出为平面补丁（快速）"),
        ),
    },
    "nurbs": {
        "name": "NURBS曲面",
        "def": "Mesh",
        "items": (
            ("None", "忽略", "忽略NURBS曲面"),
            ("Mesh", "网格", "将NURBS转换为网格，导出为笔刷"),
            (
                "Def2",
                "动态",
                "将NURBS导出为patchDef2补丁"
                "（动态细分）\n\n为了在Blender中获得更好的预览："
                "\n启用贝塞尔曲线、端点，并将阶数设置为3x3"
                "\n选择所有点并将其W值设置为100或更高",
            ),
            (
                "Def3",
                "固定",
                "将NURBS导出为patchDef3补丁"
                "（显式细分）\n\n为了在Blender中获得更好的预览："
                "\n启用贝塞尔曲线、端点，并将阶数设置为3x3"
                "\n选择所有点并将其W值设置为100或更高",
            ),
        ),
    },
    "lights": {
        "name": "灯光",
        "def": "Auto",
        "items": (
            ("None", "忽略", "忽略灯光对象"),
            (
                "Auto",
                "自适应",
                "导出灯光，近似强度"
                "\n\n尝试通过缩放场景比例来匹配灯光的外观。"
                "\n注意，对于1:1比例的导出，灯光强度"
                "可能需要达到数千。"
                "\n\n聚光灯会自动获得目标。"
                "\n通过选择'Doom 3'作为笔刷平面格式，可以导出idTech4格式的灯光",
            ),
            (
                "AsIs",
                "原样",
                "导出灯光，按原样使用强度"
                "\n\n与'自适应'相同，但强度将按原样使用。"
                "\n主要用于导入的地图和预设灯光",
            ),
        ),
    },
    "empties": {
        "name": "空物体",
        "def": "Point",
        "items": (
            ("None", "忽略", "忽略空物体"),
            (
                "Point",
                "实体",
                "将空物体导出为点实体"
                "\n\n使用对象名称作为'classname'，旋转作为'angles'"
                "以及自定义对象属性作为键/值对"
                "\n这也会导出摄像机，保持其方向",
            ),
        ),
    },
    "grid": {"name": "网格", "def": 1.0, "desc": "坐标捕捉的网格大小\n(0 = 不捕捉)"},
    "depth": {
        "name": "深度",
        "def": 2.0,
        "desc": "挤压、金字塔顶点和地形底部的偏移量"
        "\n\n使用较大网格时，请确保也增加此值",
    },
    "scale": {
        "name": "比例",
        "def": 1.0,
        "desc": "所有3D坐标的比例因子"
        "\n\n1个Quake单位约等于1英寸"
        "\n对于以米为单位的场景，比例约为40-48比较合适",
    },
    "fp": {"name": "精度", "def": 5, "desc": "小数位数"},
    "brush": {
        "name": "平面",
        "def": "Quake",
        "items": (
            (
                "Quake",
                "Quake",
                "笔刷平面为三个顶点" "\n(Quake, Half-Life, Quake 2, Quake 3)",
            ),
            ("Doom3", "Doom 3", "笔刷平面为法线+距离" "\n(Doom 3, Quake 4)"),
        ),
    },
    "uv": {
        "name": "UV映射",
        "def": "Valve",
        "items": (
            ("Quake", "标准", "世界对齐纹理投影"),
            ("Valve", "Valve", "边缘绑定纹理投影"),
            ("BPrim", "基元", "平面绑定纹理投影"),
        ),
    },
    "flags": {
        "name": "标志",
        "def": "None",
        "items": (
            ("None", "无", "无标志" "\n(Quake, Half-Life, Quake 4)"),
            (
                "Q2",
                "Quake 2",
                "内容、表面、值"
                "\n(Quake 2, Quake 3, Doom 3)"
                "\n\n为以下项目的面设置Detail标志："
                "\n - 面映射，\n - 对象，\n - 或集合"
                "\n名称中包含'detail'",
            ),
        ),
    },
    "dest": {
        "name": "输出",
        "def": "File",
        "items": (
            ("File", "文件", "保存为.map文件"),
            ("Clip", "文本", "存储在文本剪贴板中" "\n\n然后可以粘贴到TrenchBroom中"),
            (
                "GTK",
                "GTK",
                "存储在GTK剪贴板中" "\n\n然后可以粘贴到GTKRadiant、NetRadiant等",
            ),
        ),
    },
    "group": {
        "name": "分组",
        "def": "Gen",
        "items": (
            ("None", "无", "导出松散的worldspawn笔刷"),
            (
                "Auto",
                "Blender",
                "按对象/集合名称分组"
                "\n\n名称后的尾随数字将被删除\n"
                "对于要保持未分组的对象，使用'worldspawn'名称",
            ),
            ("Gen", "通用", "按通用类名分组（在下面设置）"),
        ),
    },
    "gname": {
        "name": "通用类名",
        "def": "func_group",
        "desc": "笔刷实体的类名，除非另有设置" "\n\n例如：\nfunc_group\nfunc_detail",
    },
    "skip": {
        "name": "通用材质",
        "def": "skip",
        "desc": "用于新面和未分配面的材质" "\n\n例如：\nskip\ntextures/common/caulk",
    },
    "size": {
        "name": "通用尺寸",
        "def": "64",
        "items": (
            ("16", "16", ""),
            ("32", "32", ""),
            ("64", "64", ""),
            ("128", "128", ""),
            ("256", "256", ""),
            ("512", "512", ""),
            ("1024", "1024", ""),
        ),
        "desc": "没有纹理贴图的材质的UV缩放通用尺寸",
    },
    "soup_dir": {
        "name": "地形方向",
        "def": "-Z",
        "items": (
            ("-Z", "-Z方向", "使用Z轴负方向作为地形底部（默认）"),
            ("+Z", "+Z方向", "使用Z轴正方向作为地形底部"),
            ("-X", "-X方向", "使用X轴负方向作为地形底部"),
            ("+X", "+X方向", "使用X轴正方向作为地形底部"),
            ("-Y", "-Y方向", "使用Y轴负方向作为地形底部"),
            ("+Y", "+Y方向", "使用Y轴正方向作为地形底部"),
        ),
        "desc": "选择地形(Soup)挤压的参考方向",
    },
    "miter_method": {
        "name": "外壳计算",
        "def": "Weighted",
        "items": (
            ("Weighted", "加权法线", "使用加权平均法线计算（更平滑的结果）"),
            ("Legacy", "原始算法", "使用原始的顶点法线和shell因子（更快但可能有缝隙）"),
        ),
        "desc": "选择外壳(Miter)模式下的法线计算方法",
    },
}


class ExportQuakeMapObjectPanel(bpy.types.Panel):
    bl_idname = "OBJECT_PT_QMAP_Props"
    bl_label = "Map地图导出"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        self.layout.prop(context.active_object, "qmap_geo_type")


class _ExportDefaults:
    def __getattr__(self, name):
        if name in ptxt:
            return ptxt[name]["def"]
        raise AttributeError(name)


_EXPORT_DEFAULTS = _ExportDefaults()


class _ExportPrefsAdapter:
    def __init__(self, prefs):
        self._prefs = prefs

    def __getattr__(self, name):
        return getattr(self._prefs, f"export_{name}")

    def __setattr__(self, name, value):
        if name == "_prefs":
            super().__setattr__(name, value)
        else:
            setattr(self._prefs, f"export_{name}", value)


def _addon_name():
    return __package__.split(".", 1)[0] if __package__ else __name__


def _export_prefs():
    for addon_name in (_addon_name(), __name__):
        addon = bpy.context.preferences.addons.get(addon_name)
        if addon and hasattr(addon.preferences, "export_geo"):
            return _ExportPrefsAdapter(addon.preferences)
    return _EXPORT_DEFAULTS


class ExportQuakeMap(bpy.types.Operator, ExportHelper):
    bl_idname = "export.map"
    bl_label = bl_info["name"]
    bl_description = bl_info["description"]
    bl_options = {"UNDO", "PRESET"}
    filename_ext = ".map"
    filter_glob: StringProperty(default="*.map", options={"HIDDEN"})
    prefs = _export_prefs()

    option_sel: BoolProperty(
        name=ptxt["sel"]["name"], default=prefs.sel, description=ptxt["sel"]["desc"]
    )
    option_tm: BoolProperty(
        name=ptxt["tm"]["name"], default=prefs.tm, description=ptxt["tm"]["desc"]
    )
    option_mod: BoolProperty(
        name=ptxt["mod"]["name"], default=prefs.mod, description=ptxt["mod"]["desc"]
    )
    option_tj: BoolProperty(
        name=ptxt["tj"]["name"], default=prefs.tj, description=ptxt["tj"]["desc"]
    )
    option_geo: EnumProperty(
        name=ptxt["geo"]["name"], default=prefs.geo, items=ptxt["geo"]["items"]
    )
    option_nurbs: EnumProperty(
        name=ptxt["nurbs"]["name"], default=prefs.nurbs, items=ptxt["nurbs"]["items"]
    )
    option_lights: EnumProperty(
        name=ptxt["lights"]["name"], default=prefs.lights, items=ptxt["lights"]["items"]
    )
    option_empties: EnumProperty(
        name=ptxt["empties"]["name"],
        default=prefs.empties,
        items=ptxt["empties"]["items"],
    )
    option_grid: FloatProperty(
        name=ptxt["grid"]["name"],
        min=0,
        default=prefs.grid,
        description=ptxt["grid"]["desc"],
    )
    option_depth: FloatProperty(
        name=ptxt["depth"]["name"],
        default=prefs.depth,
        description=ptxt["depth"]["desc"],
    )
    option_scale: FloatProperty(
        name=ptxt["scale"]["name"],
        default=prefs.scale,
        description=ptxt["scale"]["desc"],
    )
    option_fp: IntProperty(
        name=ptxt["fp"]["name"],
        min=0,
        soft_max=17,
        default=prefs.fp,
        description=ptxt["fp"]["desc"],
    )
    option_brush: EnumProperty(
        name=ptxt["brush"]["name"], default=prefs.brush, items=ptxt["brush"]["items"]
    )
    option_uv: EnumProperty(
        name=ptxt["uv"]["name"], default=prefs.uv, items=ptxt["uv"]["items"]
    )
    option_flags: EnumProperty(
        name=ptxt["flags"]["name"], default=prefs.flags, items=ptxt["flags"]["items"]
    )
    option_dest: EnumProperty(
        name=ptxt["dest"]["name"], default=prefs.dest, items=ptxt["dest"]["items"]
    )
    option_group: EnumProperty(
        name=ptxt["group"]["name"], default=prefs.group, items=ptxt["group"]["items"]
    )
    option_gname: StringProperty(
        name=ptxt["gname"]["name"],
        default=prefs.gname,
        description=ptxt["gname"]["desc"],
    )
    option_skip: StringProperty(
        name=ptxt["skip"]["name"], default=prefs.skip, description=ptxt["skip"]["desc"]
    )
    option_size: EnumProperty(
        name=ptxt["size"]["name"],
        default=prefs.size,
        items=ptxt["size"]["items"],
        description=ptxt["size"]["desc"],
    )
    option_soup_dir: EnumProperty(
        name=ptxt["soup_dir"]["name"],
        default=prefs.soup_dir,
        items=ptxt["soup_dir"]["items"],
        description=ptxt["soup_dir"]["desc"],
    )
    option_miter_method: EnumProperty(
        name=ptxt["miter_method"]["name"],
        default=prefs.miter_method,
        items=ptxt["miter_method"]["items"],
        description=ptxt["miter_method"]["desc"],
    )

    # all encountered names, including duplicates
    seen_names = []
    # offset spotlight targets by 64 units, regardless of chosen scale
    spot_name, spot_class, spot_offset = "spot_target_", "info_null", 64
    # export cameras as point entities, match entity's +X to camera's -Z
    cam_correct = Euler((-math.pi / 2, 0, math.pi / 2), "ZXY").to_matrix().to_4x4()

    def draw(self, context):
        o = "option_"
        self.layout.separator()
        spl = self.layout.row().split(factor=0.5)
        col = spl.column()
        for p in [o + "sel", o + "tm"]:
            col.prop(self, p)
        col = spl.column()
        for p in [o + "mod", o + "tj"]:
            col.prop(self, p)
        self.layout.separator()
        self.layout.label(text="Object types", icon="SCENE_DATA")
        spl = self.layout.row().split(factor=0.5)
        col = spl.column()
        for p in [o + "geo", o + "nurbs"]:
            col.prop(self, p)
        col = spl.column()
        for p in [o + "lights", o + "empties"]:
            col.prop(self, p)
        self.layout.separator()
        self.layout.label(text="Coordinates", icon="MESH_DATA")
        spl = self.layout.row().split(factor=0.5)
        col = spl.column()
        for p in [o + "grid", o + "depth"]:
            col.prop(self, p)
        col = spl.column()
        for p in [o + "scale", o + "fp"]:
            col.prop(self, p)
        self.layout.separator()
        self.layout.label(text="Output format", icon="UV_DATA")
        spl = self.layout.row().split(factor=0.5)
        col = spl.column()
        for p in [o + "brush", o + "uv"]:
            col.prop(self, p)
        col = spl.column()
        for p in [o + "flags", o + "dest"]:
            col.prop(self, p)
        self.layout.separator()
        self.layout.label(text="Miscellaneous", icon="GROUP")
        col = self.layout.column()
        col.prop(self, o + "group")
        col.prop(self, o + "gname", text="Class")
        col.prop(self, o + "skip", text="Material")
        col.prop(self, o + "size", text="Tex size")

        # 显示Soup方向选择
        if self.option_geo == "Soup":
            col.prop(self, o + "soup_dir")

        # 显示Miter计算方法选择
        if self.option_geo == "Miter":
            col.prop(self, o + "miter_method")

    def entname(self, ent):
        if self.option_group == "None":
            return ""
        elif self.option_group == "Gen":
            tname = self.option_gname
        elif self.option_group == "Auto":
            tname = ent.name.rstrip("0123456789")
            tname = tname[:-1] if tname[-1] in (".", " ") else ent.name

        name = '}\n{\n"classname" "' + tname + '"\n'
        if self.option_brush == "Doom3":
            self.seen_names.append(tname)
            n_name = self.seen_names.count(tname)
            name += '"name" "' + tname + f'_{n_name}"\n'
            name += '"model" "' + tname + f'_{n_name}"\n'
        return name

    def gridsnap(self, vector):
        grid = self.option_grid
        if grid:
            return [round(co / grid) * grid for co in vector]
        else:
            return vector

    def printvec(self, vector):
        fstring = []
        for co in vector:
            fstring.append(fformat(co, precision=self.option_fp, trim="-"))
        return " ".join(fstring)

    def brushplane(self, face):
        if self.option_brush == "Quake":
            planestring = ""
            for vert in reversed(face.verts[0:3]):
                planestring += f"( {self.printvec(vert.co)} ) "
            return planestring
        elif self.option_brush == "Doom3":
            # more accurate than just the dot product
            dist = geometry.distance_point_to_plane(
                (0.0, 0.0, 0.0), face.verts[0].co, face.normal
            )
            return f"( {self.printvec([co for co in face.normal] + [dist])} ) "

    def faceflags(self, face, mesh, obj):
        if self.option_flags == "None":
            return "\n"
        elif self.option_flags == "Q2":
            col = obj.users_collection[0]
            if bpy.app.version < (4, 0, 0) and len(obj.face_maps) > 0:
                obj.face_maps.new()  # faces w/o face maps have index -1 (?)
                fm_layer = mesh.faces.layers.face_map.verify()
                fm_name = obj.face_maps[face[fm_layer]].name
                obj.face_maps.remove(obj.face_maps[-1])
            else:
                fm_name = ""
            # Blender 4.0.0 does not provide python access to bool attributes
            # so iterate over floats/strings/etc and treat non-zero as true
            f_attr_names = []
            for f_attrs_of_type in [
                getattr(mesh.faces.layers, dtype)
                for dtype in dir(mesh.faces.layers)
                if not dtype.startswith("__")
            ]:
                for f_attr_name in f_attrs_of_type.keys():
                    if face[f_attrs_of_type.get(f_attr_name)]:
                        f_attr_names.append(f_attr_name)

            names = obj.name + col.name + fm_name + "".join(f_attr_names)
            if "detail" in names.lower():
                return f" {1<<27} 0 0\n"
            else:
                return " 0 0 0\n"

    def get_udim_tile_from_uv(self, uv_coord):
        """根据UV坐标计算UDIM瓦片编号"""
        u, v = uv_coord
        
        # UDIM瓦片编号计算：1001 + u_tile + v_tile * 10
        u_tile = int(u)  # U方向的瓦片索引
        v_tile = int(v)  # V方向的瓦片索引
        
        # 确保在有效范围内
        u_tile = max(0, min(9, u_tile))  # 限制在0-9范围
        v_tile = max(0, min(9, v_tile))  # 限制在0-9范围
        
        tile_number = 1001 + u_tile + v_tile * 10
        return tile_number
    
    def get_base_color_texture_name(self, mat):
        """获取Base Color连接的纹理名称"""
        if not mat or not mat.use_nodes:
            return None
        
        # 查找Principled BSDF节点
        for node in mat.node_tree.nodes:
            if node.type == "BSDF_PRINCIPLED":
                # 检查Base Color输入是否连接了纹理
                base_color_input = node.inputs.get("Base Color")
                if base_color_input and base_color_input.is_linked:
                    from_node = base_color_input.links[0].from_node
                    if from_node.type == "TEX_IMAGE" and from_node.image:
                        image = from_node.image
                        if hasattr(image, 'filepath') and image.filepath:
                            # 获取文件路径并提取文件名
                            import os
                            filepath = image.filepath
                            # 处理Blender的相对路径
                            if filepath.startswith('//'):
                                filepath = bpy.path.abspath(filepath)
                            filename = os.path.basename(filepath)
                            if filename:
                                # 移除UDIM占位符
                                filename = filename.replace('<UDIM>', '').replace('.<UDIM>', '')
                                # 清理可能的双点号
                                filename = filename.replace('..', '.')
                                # 移除扩展名
                                if '.' in filename:
                                    name_without_ext = filename.rsplit('.', 1)[0]
                                    return name_without_ext
                                else:
                                    return filename
                        elif hasattr(image, 'name') and image.name:
                            # 如果没有文件路径，使用图像名称
                            filename = image.name
                            # 移除UDIM占位符
                            filename = filename.replace('<UDIM>', '').replace('.<UDIM>', '')
                            # 清理可能的双点号
                            filename = filename.replace('..', '.')
                            # 移除扩展名
                            if '.' in filename:
                                name_without_ext = filename.rsplit('.', 1)[0]
                                return name_without_ext
                            else:
                                return filename
                break
        return None

    def is_material_using_udim(self, mat):
        """检查材质是否使用UDIM纹理"""
        if not mat or not mat.use_nodes:
            return False
        
        # 查找Principled BSDF节点
        for node in mat.node_tree.nodes:
            if node.type == "BSDF_PRINCIPLED":
                base_color_input = node.inputs.get("Base Color")
                if base_color_input and base_color_input.is_linked:
                    from_node = base_color_input.links[0].from_node
                    if from_node.type == "TEX_IMAGE" and from_node.image:
                        # 检查是否为UDIM纹理
                        image = from_node.image
                        # 首先检查Blender的内置UDIM标识
                        if hasattr(image, 'source') and image.source == 'TILED':
                            return True
                        
                        # 检查文件路径中的UDIM模式
                        if hasattr(image, 'filepath') and image.filepath:
                            import os
                            filepath = image.filepath.lower()
                            filename = os.path.basename(filepath)
                            
                            # 检查是否包含<udim>占位符
                            if '<udim>' in filepath:
                                return True
                            
                            # 更精确的UDIM瓦片编号检测：
                            # 只有当数字前后有分隔符（如点、下划线）或在文件名末尾时才认为是UDIM
                            import re
                            # 匹配模式：分隔符+4位数字(1001-1099)+分隔符或文件扩展名
                            udim_pattern = r'[._-](10[0-9][0-9])(?=[._-]|$|\.[a-zA-Z]+$)'
                            if re.search(udim_pattern, filename):
                                return True
                break
        return False

    def texdata(self, face, mesh, obj, material_index=None):
        mat = None
        texstring = self.option_skip
        width = height = int(self.option_size)
        if material_index is None:
            material_index = face.material_index
        if obj.material_slots and material_index < len(obj.material_slots):
            mat = obj.material_slots[material_index].material
        if mat:
            if mat.node_tree:
                for node in mat.node_tree.nodes:
                    if node.type == "TEX_IMAGE":
                        if node.image and node.image.has_data:
                            width, height = node.image.size
                            break

            # 获取UV坐标用于UDIM判定
            uv_layer = mesh.loops.layers.uv.active
            if uv_layer is None:
                uv_layer = mesh.loops.layers.uv.new("dummy")
            first_uv = face.loops[0][uv_layer].uv

            # 尝试获取Base Color连接的纹理名称
            texture_name = self.get_base_color_texture_name(mat)
            if texture_name:
                base_name = texture_name.replace(" ", "_")
            else:
                base_name = mat.name.replace(" ", "_")

            # 检查是否为UDIM纹理
            if self.is_material_using_udim(mat):
                # 根据UV坐标确定UDIM瓦片
                tile_number = self.get_udim_tile_from_uv(first_uv)
                # UDIM格式：base_name.tile_number（不添加.bmp后缀）
                texstring = f"{base_name}.{tile_number}"
            else:
                texstring = base_name
        if self.option_brush == "Doom3":
            texstring = f'"{texstring}"'

        V = [loop.vert.co for loop in face.loops]
        uv_layer = mesh.loops.layers.uv.active
        if uv_layer is None:
            uv_layer = mesh.loops.layers.uv.new("dummy")
        T = [loop[uv_layer].uv for loop in face.loops]

        if self.option_uv == "Valve":
            # [ Ux Uy Uz Uoffs ] [ Vx Vy Vz Voffs ] rotation scaleU scaleV
            dummy = " [ 1 0 0 0 ] [ 0 -1 0 0 ] 0 1 1"

            # ported from: https://bitbucket.org/khreathor/obj-2-map
            # Set up "2d world" coordinate system with the 01 edge along X
            world01 = V[1] - V[0]
            world02 = V[2] - V[0]
            world01_02Angle = world01.angle(world02)
            if face.normal.dot(world01.cross(world02)) < 0:
                world01_02Angle = -world01_02Angle
            world01_2d = Vector((world01.length, 0.0))
            world02_2d = (
                Vector((math.cos(world01_02Angle), math.sin(world01_02Angle)))
                * world02.length
            )

            # Get 01 and 02 vectors in UV space and scale them
            tex01 = T[1] - T[0]
            tex02 = T[2] - T[0]
            tex01.x *= width
            tex02.x *= width
            tex01.y *= height
            tex02.y *= height

            """
            a = world01_2d
            b = world02_2d
            p = tex01
            q = tex02

            [ px ]   [ m11 m12 0 ] [ ax ]
            [ py ] = [ m21 m22 0 ] [ ay ]
            [ 1  ]   [ 0   0   1 ] [ 1  ]

            [ qx ]   [ m11 m12 0 ] [ bx ]
            [ qy ] = [ m21 m22 0 ] [ by ]
            [ 1  ]   [ 0   0   1 ] [ 1  ]

            px = ax * m11 + ay * m12
            py = ax * m21 + ay * m22
            qx = bx * m11 + by * m12
            qy = bx * m21 + by * m22

            [ px ]   [ ax ay 0  0  ] [ m11 ]
            [ py ] = [ 0  0  ax ay ] [ m12 ]
            [ qx ]   [ bx by 0  0  ] [ m21 ]
            [ qy ]   [ 0  0  bx by ] [ m22 ]
            """

            # Find an affine transformation to convert
            # world01_2d and world02_2d to their respective UV coords
            texCoordsVec = Vector((tex01.x, tex01.y, tex02.x, tex02.y))
            world2DMatrix = Matrix(
                (
                    (world01_2d.x, world01_2d.y, 0, 0),
                    (0, 0, world01_2d.x, world01_2d.y),
                    (world02_2d.x, world02_2d.y, 0, 0),
                    (0, 0, world02_2d.x, world02_2d.y),
                )
            )
            try:
                mCoeffs = solve(world2DMatrix, texCoordsVec)
            except:
                return texstring + dummy
            right_2dworld = Vector(mCoeffs[0:2])
            up_2dworld = Vector(mCoeffs[2:4])

            # These are the final scale values
            # (avoid division by 0 for degenerate or missing UVs)
            scalex = 1 / max(0.00001, right_2dworld.length)
            scaley = 1 / max(0.00001, up_2dworld.length)
            scale = Vector((scalex, scaley))

            # Get the angles of the texture axes. These are in the 2d world
            # coordinate system, so they're relative to the 01 vector
            right_2dworld_angle = math.atan2(right_2dworld.y, right_2dworld.x)
            up_2dworld_angle = math.atan2(up_2dworld.y, up_2dworld.x)

            # Recreate the texture axes in 3d world coordinates,
            # using the angles from the 01 edge
            rt = world01.normalized()
            up = rt.copy()
            rt.rotate(Matrix.Rotation(right_2dworld_angle, 3, face.normal))
            up.rotate(Matrix.Rotation(up_2dworld_angle, 3, face.normal))

            # Now we just need the offsets
            rt_full = rt.to_4d()
            up_full = up.to_4d()
            test_s = V[0].dot(rt) / (width * scale.x)
            test_t = V[0].dot(up) / (height * scale.y)
            rt_full[3] = (T[0].x - test_s) * width
            up_full[3] = (T[0].y - test_t) * height

            texstring += (
                f" [ {self.printvec(rt_full)} ]"
                f" [ {self.printvec(up_full)} ]"
                f" 0 {self.printvec(scale)}"
            )

        elif self.option_uv == "Quake":
            # offsetU offsetV rotation scaleU scaleV
            dummy = " 0 0 0 1 1"

            # 01 and 02 in 3D space
            world01 = V[1] - V[0]
            world02 = V[2] - V[0]

            # 01 and 02 projected along the closest axis
            maxn = max(abs(round(co, self.option_fp)) for co in face.normal)
            for i in [2, 0, 1]:  # axis priority for 45 degree angles
                if round(abs(face.normal[i]), self.option_fp) == maxn:
                    axis = i
                    break
            world01_2d = Vector((world01[:axis] + world01[(axis + 1) :]))
            world02_2d = Vector((world02[:axis] + world02[(axis + 1) :]))

            # 01 and 02 in UV space (scaled to texture size)
            tex01 = T[1] - T[0]
            tex02 = T[2] - T[0]
            tex01.x *= width
            tex02.x *= width
            tex01.y *= height
            tex02.y *= height

            # Find affine transformation between 2D and UV
            texCoordsVec = Vector((tex01.x, tex01.y, tex02.x, tex02.y))
            world2DMatrix = Matrix(
                (
                    (world01_2d.x, world01_2d.y, 0, 0),
                    (0, 0, world01_2d.x, world01_2d.y),
                    (world02_2d.x, world02_2d.y, 0, 0),
                    (0, 0, world02_2d.x, world02_2d.y),
                )
            )
            try:
                mCoeffs = solve(world2DMatrix, texCoordsVec)
            except:
                return texstring + dummy

            # Build the transformation matrix and decompose it
            tformMtx = Matrix(
                ((mCoeffs[0], mCoeffs[1], 0), (mCoeffs[2], mCoeffs[3], 0), (0, 0, 1))
            )
            rotation = math.degrees(tformMtx.inverted_safe().to_euler().z)
            scale = tformMtx.inverted_safe().to_scale()  # never zero
            scale.x *= math.copysign(1, tformMtx.determinant())

            # Calculate offsets
            t0 = Vector((T[0].x * width, T[0].y * height))
            v0 = Vector((V[0][:axis] + V[0][(axis + 1) :]))
            v0.rotate(Matrix.Rotation(math.radians(-rotation), 2))
            v0 = Vector((v0.x / scale.x, v0.y / scale.y))
            offset = t0 - v0
            offset.y *= -1  # v is flipped

            finvals = [offset.x, offset.y, rotation, scale.x, scale.y]
            texstring += f" {self.printvec(finvals)}"

        elif self.option_uv == "BPrim":
            # ( ( a1 a2 a3 ) ( a4 a5 a6 ) )
            dummy = "( ( 0.0078125 0 0 ) ( 0 0.0078125 0 ) ) "
            """
            Brush Primitives format

            t = A * B * v, where:
            t is the vertex in UV
            v is the same vertex in 3D
            B transforms world space so that X axis points along face normal
            A is a homogenous matrix that transforms this new space to UV

            B has to match the one arbitrarily chosen in editor and compiler
            A has first two rows stored in map file and third row as (0 0 1)

            t[i] = A * (B * v[i]) = A * vb[i]

            for every vertex:
            [ u ]   [ a1 a2 a3 ] [ xb ]
            [ v ] = [ a4 a5 a6 ] [ yb ]
            [ 1 ]   [ 0  0  1  ] [ zb ]

            1 = zb
            u = a1*xb + a2*yb + a3
            v = a4*xb + a5*yb + a6

            three verts, six unknowns, six equations
            [ u1 ]   [ x1b y1b 1   0   0   0 ] [ a1 ]
            [ v1 ] = [ 0   0   0   x1b y1b 1 ] [ a2 ]
            [ u2 ]   [ x2b y2b 1   0   0   0 ] [ a3 ]
            [ v2 ] = [ 0   0   0   x2b y2b 1 ] [ a4 ]
            [ u3 ]   [ x3b y3b 1   0   0   0 ] [ a5 ]
            [ v3 ] = [ 0   0   0   x3b y3b 1 ] [ a6 ]
            """
            n = face.normal
            # angle between the X axis and normal's projection onto XY plane
            if abs(n.x) > 1e-6 or abs(n.y) > 1e-6:
                theta_z = math.atan2(n.y, n.x)
            else:
                theta_z = 0
            # angle between the normal and its projection onto XY plane
            theta_y = math.atan2(n.z, math.sqrt(n.x**2 + n.y**2))

            # Brush Primitives specific matrix B, spins world around Z and Y
            b11 = -math.sin(theta_z)
            b12 = math.cos(theta_z)
            b21 = math.sin(theta_y) * math.cos(theta_z)
            b22 = math.sin(theta_y) * math.sin(theta_z)
            b23 = -math.cos(theta_y)
            B = Matrix(((b11, b12, 0), (b21, b22, b23), (0, 0, 0)))
            VB = [B @ vert for vert in V]

            # v is flipped
            T6 = [T[0].x, -T[0].y, T[1].x, -T[1].y, T[2].x, -T[2].y]

            M6 = [
                [VB[0].x, VB[0].y, 1, 0, 0, 0],
                [0, 0, 0, VB[0].x, VB[0].y, 1],
                [VB[1].x, VB[1].y, 1, 0, 0, 0],
                [0, 0, 0, VB[1].x, VB[1].y, 1],
                [VB[2].x, VB[2].y, 1, 0, 0, 0],
                [0, 0, 0, VB[2].x, VB[2].y, 1],
            ]
            try:
                A6 = solve(M6, T6)
            except:
                return dummy + texstring
            if (abs(A6[0]) < 1e-9 and abs(A6[1]) < 1e-9) or (
                abs(A6[3]) < 1e-9 and abs(A6[4]) < 1e-9
            ):
                return dummy + texstring
            # unlike other formats, coordinates go before the material name
            texstring = (
                f"( ( {self.printvec(A6[0:3])} )"
                f"  ( {self.printvec(A6[3:6])} ) ) " + texstring
            )
        return texstring

    def is_nonplanar_quad(self, face):
        if len(face.verts) != 4:
            return False

        verts = [vert.co for vert in face.verts]
        normal = (verts[1] - verts[0]).cross(verts[2] - verts[0])
        if normal.length_squared < 1e-12:
            return False

        distance = abs((verts[3] - verts[0]).dot(normal.normalized()))
        return distance > 1e-9

    def write_brush_from_faces(
        self, source_faces, source_uv_layer, obj, fw, template, visible_face=None
    ):
        pbm = bmesh.new()
        vmap = {}
        try:
            target_uv_layer = None
            if source_uv_layer is not None:
                target_uv_layer = pbm.loops.layers.uv.new("UVMap")

            visible_source_index = visible_face.index if visible_face is not None else None
            visible_material_index = visible_face.material_index if visible_face is not None else None

            for source_face in source_faces:
                verts = []
                for vert in source_face.verts:
                    if vert.index not in vmap:
                        vmap[vert.index] = pbm.verts.new(
                            Vector(self.gridsnap(vert.co * self.option_scale))
                        )
                    verts.append(vmap[vert.index])
                try:
                    face = pbm.faces.new(verts)
                except ValueError:
                    continue
                face.material_index = (
                    source_face.material_index
                    if visible_source_index is None or source_face.index == visible_source_index
                    else len(obj.data.materials) - 1
                )
                if target_uv_layer is not None:
                    for source_loop, target_loop in zip(source_face.loops, face.loops):
                        target_loop[target_uv_layer].uv = source_loop[source_uv_layer].uv

            pbm.verts.ensure_lookup_table()
            pbm.faces.ensure_lookup_table()
            bmesh.ops.recalc_face_normals(pbm, faces=pbm.faces)
            bmesh.ops.join_triangles(
                pbm, faces=pbm.faces, angle_face_threshold=0.01, angle_shape_threshold=0.7
            )
            nonplanar_quads = [
                face
                for face in pbm.faces
                if len(face.verts) == 4 and self.is_nonplanar_quad(face)
            ]
            if nonplanar_quads:
                bmesh.ops.triangulate(pbm, faces=nonplanar_quads, quad_method="LONG_EDGE")
            bmesh.ops.connect_verts_nonplanar(pbm, faces=pbm.faces, angle_limit=0.0)
            bmesh.ops.recalc_face_normals(pbm, faces=pbm.faces)

            skip_material_index = len(obj.data.materials) - 1
            visible_faces = (
                [face for face in pbm.faces if face.material_index != skip_material_index]
                if visible_source_index is not None
                else [None]
            )
            for visible_output_face in visible_faces:
                fw(template[0])
                for face in pbm.faces:
                    material_index = (
                        visible_material_index
                        if visible_output_face is None or face == visible_output_face
                        else skip_material_index
                    )
                    fw(self.brushplane(face))
                    fw(self.texdata(face, pbm, obj, material_index) + "\n")
                fw(template[1])
        finally:
            pbm.free()

    def coplanar_faces(self, face_a, face_b):
        if face_a.normal.dot(face_b.normal) < 1.0 - 1e-5:
            return False
        return abs(face_a.normal.dot(face_b.verts[0].co - face_a.verts[0].co)) <= 1e-4

    def split_array_visible_faces(self, faces, visible_material_index):
        visible_faces = [
            face
            for face in faces
            if face.material_index == visible_material_index and face.calc_area() > 1e-4
        ]
        if not visible_faces:
            return []
        axis = {"-X": 0, "+X": 0, "-Y": 1, "+Y": 1}.get(self.option_soup_dir, 2)
        return [max(visible_faces, key=lambda face: abs(face.normal[axis]))]

    def process_array_prisms(self, bm, obj, orig_obj, fw, template):
        bm.verts.ensure_lookup_table()
        bm.verts.index_update()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        bm.faces.index_update()

        edge_face_count = defaultdict(int)
        for face in bm.faces:
            for edge in face.edges:
                edge_face_count[edge] += 1

        sections = [
            face
            for face in bm.faces
            if len(face.verts) >= 3
            and face.calc_area() > 1e-4
            and len({edge_face_count[edge] for edge in face.edges}) == 1
        ]
        if len(sections) < 2:
            self.report({"WARNING"}, "Array Prisms needs at least two section faces")
            return

        section_by_vert = {}
        for section_index, section in enumerate(sections):
            for vert in section.verts:
                section_by_vert[vert.index] = section_index

        pair_faces = defaultdict(list)
        for face in bm.faces:
            if len(face.verts) != 4:
                continue
            counts = {}
            for vert in face.verts:
                section_index = section_by_vert.get(vert.index)
                if section_index is not None:
                    counts[section_index] = counts.get(section_index, 0) + 1
            if len(counts) == 2 and sorted(counts.values()) == [2, 2]:
                pair_faces[tuple(sorted(counts))].append(face)

        adjacency = defaultdict(list)
        for (a, b), faces in pair_faces.items():
            if len(faces) == min(len(sections[a].verts), len(sections[b].verts)):
                adjacency[a].append(b)
                adjacency[b].append(a)

        source_uv_layer = bm.loops.layers.uv.active
        visited = set()
        exported_count = 0

        for start in [i for i in range(len(sections)) if len(adjacency[i]) == 1]:
            if start in visited:
                continue

            order = []
            previous = None
            current = start
            while True:
                order.append(current)
                visited.add(current)
                next_items = [item for item in adjacency[current] if item != previous]
                if not next_items:
                    break
                previous, current = current, next_items[0]

            if len(order) < 2 or len(adjacency[order[-1]]) != 1:
                continue

            for a, b in zip(order, order[1:]):
                key = tuple(sorted((a, b)))
                segment_faces = [sections[a], sections[b], *pair_faces[key]]
                self.write_brush_from_faces(
                    segment_faces,
                    source_uv_layer,
                    obj,
                    fw,
                    template,
                )
                exported_count += 1

        if exported_count == 0:
            self.report({"WARNING"}, "Array Prisms could not find any section chain")

    def process_mesh(self, obj, fw, template):
        geo_type = obj.qmap_geo_type
        if geo_type == "Default":
            geo_type = self.option_geo
        origin = self.gridsnap(obj.matrix_world.translation)
        obj.data.materials.append(None)  # empty slot for new faces
        orig_obj = obj
        if self.option_mod or obj.type != "MESH":
            obj = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        bm = bmesh.new()
        bm.from_mesh(obj.to_mesh())
        if self.option_tm:
            bmesh.ops.transform(bm, matrix=obj.matrix_world, verts=bm.verts)

        if geo_type != "ArrayPrisms":
            for vert in bm.verts:
                vert.co = self.gridsnap(vert.co * self.option_scale)
        
        # Calculate mesh center for Blob mode
        if geo_type == "Blob" and bm.verts:
            mesh_center = Vector((0, 0, 0))
            for vert in bm.verts:
                mesh_center += vert.co
            mesh_center /= len(bm.verts)
            mesh_center = self.gridsnap(mesh_center)

        if geo_type == "ArrayPrisms":  # export triangular section chains as prism brushes
            self.process_array_prisms(bm, obj, orig_obj, fw, template)

        elif geo_type == "Brush":  # export entire mesh as a single brush
            hull = bmesh.ops.convex_hull(bm, input=bm.verts, use_existing_faces=True)
            geom_hull = hull["geom"] + hull["geom_holes"]
            interior = [face for face in bm.faces if face not in geom_hull]
            bmesh.ops.delete(bm, geom=interior, context="FACES")
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            bmesh.ops.join_triangles(
                bm, faces=bm.faces, angle_face_threshold=0.01, angle_shape_threshold=0.7
            )
            bmesh.ops.connect_verts_nonplanar(bm, faces=bm.faces, angle_limit=0.0)
            fw(template[0])
            for face in bm.faces:
                flags = self.faceflags(face, bm, orig_obj)
                fw(self.brushplane(face))
                fw(self.texdata(face, bm, obj) + flags)
            fw(template[1])

        elif geo_type == "Patches":  # export each face as a flat patch
            ngons = [face for face in bm.faces if len(face.loops) > 4]
            bmesh.ops.triangulate(bm, faces=ngons, quad_method='BEAUTY', ngon_method='BEAUTY')
            uv_layer = bm.loops.layers.uv.active
            if uv_layer is None:
                uv_layer = bm.loops.layers.uv.new("dummy")
            for face in bm.faces:
                mat = None
                if obj.material_slots:
                    mat = obj.material_slots[face.material_index].material
                if mat:
                    matname = mat.name.replace(" ", "_")
                else:
                    matname = self.option_skip
                if self.option_brush == "Doom3":
                    matname = f'"{matname}"'
                fw(f"{{\npatchDef2\n{{\n{matname}\n( 3 3 0 0 0 )\n(\n")
                pts = []
                for loop in face.loops:
                    pts.append(
                        f"{self.printvec(loop.vert.co)} "
                        f"{self.printvec(loop[uv_layer].uv * Vector((1,-1)))}"
                    )
                fw(f"( ( {pts[1]} ) ( {pts[1]} ) ( {pts[0]} ) )\n" * 2)
                fw(f"( ( {pts[2]} ) ( {pts[2]} ) ( {pts[len(pts)-1]} ) )\n")
                fw(")\n}\n}\n")

        else:  # export each face as a brush
            bmesh.ops.connect_verts_concave(bm, faces=bm.faces)  # concave poly
            if self.option_tj:
                tjfaces = []
                for face in bm.faces:
                    for loop in face.loops:
                        if abs(loop.calc_angle() - math.pi) <= 1e-4:
                            tjfaces.append(face)
                            break
                bmesh.ops.triangulate(bm, faces=tjfaces, quad_method='BEAUTY', ngon_method='BEAUTY')  # mid-edge verts
            nonplanar_quads = [
                face
                for face in bm.faces
                if len(face.verts) == 4 and self.is_nonplanar_quad(face)
            ]
            if nonplanar_quads:
                bmesh.ops.triangulate(bm, faces=nonplanar_quads, quad_method="LONG_EDGE")
            bmesh.ops.connect_verts_nonplanar(
                bm, faces=bm.faces, angle_limit=1e-3
            )  # concave surface
            if geo_type == "Soup":
                # 检查对象是否有自己的soup_dir设置
                if "qmap_soup_dir" in obj:
                    direction = obj["qmap_soup_dir"]
                else:
                    direction = self.option_soup_dir

                if direction == "-Z":
                    bottom = min(vert.co.z for vert in bm.verts)
                    bottom -= self.option_depth
                elif direction == "+Z":
                    bottom = max(vert.co.z for vert in bm.verts)
                    bottom += self.option_depth
                elif direction == "-X":
                    bottom = min(vert.co.x for vert in bm.verts)
                    bottom -= self.option_depth
                elif direction == "+X":
                    bottom = max(vert.co.x for vert in bm.verts)
                    bottom += self.option_depth
                elif direction == "-Y":
                    bottom = min(vert.co.y for vert in bm.verts)
                    bottom -= self.option_depth
                elif direction == "+Y":
                    bottom = max(vert.co.y for vert in bm.verts)
                    bottom += self.option_depth

            for face in bm.faces[:]:
                if face.calc_area() <= 1e-4:
                    continue
                flags = self.faceflags(face, bm, orig_obj)
                fw(template[0])
                fw(self.brushplane(face))
                fw(self.texdata(face, bm, obj) + flags)  # write original face

                if geo_type in ("Faces", "Blob"):
                    new = bmesh.ops.poke(bm, faces=[face], offset=-self.option_depth)
                    if geo_type == "Blob":
                        new["verts"][0].co = mesh_center
                    elif geo_type == "Faces":
                        new["verts"][0].co = self.gridsnap(new["verts"][0].co)

                elif geo_type in ("Prisms", "Soup", "Miter"):
                    clone = face.copy()  # keep original face & vertex normals
                    new = bmesh.ops.extrude_discrete_faces(bm, faces=[clone])
                    new_verts = new["faces"][0].verts

                    if geo_type == "Prisms":
                        bmesh.ops.translate(
                            bm, verts=new_verts, vec=face.normal * -self.option_depth
                        )
                    elif geo_type == "Soup":
                        for vert in new_verts:
                            if direction == "-Z" or direction == "+Z":
                                vert.co.z = bottom
                            elif direction == "-X" or direction == "+X":
                                vert.co.x = bottom
                            elif direction == "-Y" or direction == "+Y":
                                vert.co.y = bottom
                    elif geo_type == "Miter":
                        # 根据选择的方法应用不同的算法
                        if self.option_miter_method == "Weighted":
                            # 计算每个顶点的加权平均法线
                            vert_normals = {}
                            for v in face.verts:
                                # 收集所有相邻面
                                adjacent_faces = []
                                for f in v.link_faces:
                                    adjacent_faces.append(f)

                                # 计算加权平均法线
                                avg_normal = Vector((0, 0, 0))
                                total_weight = 0
                                for f in adjacent_faces:
                                    # 使用面积作为权重
                                    weight = f.calc_area()
                                    avg_normal += f.normal * weight
                                    total_weight += weight

                                if total_weight > 0:
                                    avg_normal /= total_weight
                                    avg_normal.normalize()
                                else:
                                    avg_normal = v.normal

                                vert_normals[v] = avg_normal

                            # 应用计算出的法线进行挤出
                            for new_v, orig_v in zip(new_verts, face.verts):
                                new_v.co -= vert_normals[orig_v] * self.option_depth
                        else:
                            # Legacy方法 - 使用原始的顶点法线和shell因子
                            for new_v, orig_v in zip(new_verts, face.verts):
                                new_v.co -= (
                                    orig_v.normal
                                    * orig_v.calc_shell_factor()
                                    * self.option_depth
                                )

                    geom = bmesh.ops.region_extend(
                        bm, use_faces=True, geom=new["faces"]
                    )
                    new["faces"].extend(geom["geom"])

                bm.normal_update()
                for newface in new["faces"]:  # write new faces
                    newface.normal_flip()
                    newface.material_index = len(obj.data.materials) - 1
                    fw(self.brushplane(newface))
                    fw(self.texdata(newface, bm, obj) + flags)
                fw(template[1])

        bm.free()
        orig_obj.data.materials.pop()  # remove the empty slot

    def process_nurbs(self, obj, spline, fw):
        mat = None
        if obj.material_slots:
            mat = obj.material_slots[spline.material_index].material
        if mat:
            matname = mat.name.replace(" ", "_")
        else:
            matname = self.option_skip
        if self.option_brush == "Doom3":
            matname = f'"{matname}"'

        wu, wv = spline.point_count_u, spline.point_count_v
        nu, nv = wu + spline.use_cyclic_u, wv + spline.use_cyclic_v
        ru, rv = spline.resolution_u + 1, spline.resolution_v + 1
        du, dv = 1 / (nu - 1), -1 / (nv - 1)  # UV increments (v is flipped)
        if nu % 2 == 0 or nv % 2 == 0 or nu == 1 or nv == 1:
            self.report({"WARNING"}, f"Skipped invalid patch {obj.name}")
            return

        fw("{\npatch" + self.option_nurbs + "\n{\n")
        fw(matname + "\n")
        if self.option_nurbs == "Def2":
            fw(f"( {nu} {nv} 0 0 0 )\n(\n")
        else:
            fw(f"( {nu} {nv} {ru} {rv} 0 0 0 )\n(\n")
        for i in range(nu):
            fw("( ")
            for j in reversed(range(nv)):
                texuv = (i * du, j * dv)
                index = (j % wv) * wu + (i % wu)
                xyz = spline.points[index].co[:3]
                if self.option_tm:
                    xyz = obj.matrix_world @ Vector(xyz)
                xyz = self.gridsnap(xyz * self.option_scale)
                fw(f"( {self.printvec(xyz)} {self.printvec(texuv)} ) ")
            fw(")\n")
        fw(")\n}\n}\n")

    def process_light(self, obj, fw):
        intensity = obj.data.energy
        origin = obj.matrix_world.to_translation() * self.option_scale
        fw('{\n"classname" "light"\n')
        fw(f'"origin" "{self.printvec(origin)}"\n')
        fw(f'"_color" "{self.printvec(obj.data.color)}"\n')
        if self.option_lights == "Auto":
            intensity *= self.option_scale**2 / 40**2  # 1 inch = 1 unit
        fw(f'"light" "{intensity}"\n')

        keys = obj.keys()
        if "delay" not in keys:
            fw(f'"delay" "2"\n')  # Q1 attenuation
        pt_size = obj.data.shadow_soft_size
        if "_deviance" not in keys and pt_size != 0.25:
            fw(f'"_deviance" "{pt_size * self.option_scale}"\n')  # Q1,Q3
        for prop in keys:  # custom object properties
            if prop not in (
                "classname",
                "origin",
                "light",
                "_color",
                "angle",
                "_softangle",
                "radius",
                "target",
            ):
                if isinstance(obj[prop], (int, float, str)):  # no arrays
                    fw(f'"{prop}" "{obj[prop]}"\n')

        if obj.data.type == "POINT":
            if self.option_brush == "Doom3":
                pt_range = intensity * 10  # eyeballed
                if "light_radius" not in keys:
                    fw(f'"light_radius" "{pt_range} {pt_range} {pt_range}"\n')
                if "texture" not in keys:
                    fw(f'"texture" "lights/falloff_exp1"\n')
        elif obj.data.type == "SPOT":
            spot_ang = obj.data.spot_size
            if self.option_brush == "Doom3":
                spot_hyp = 10 * self.option_scale
                spot_scale = obj.matrix_world.to_scale()
                spot_fw = math.cos(spot_ang / 2) * spot_hyp * spot_scale.z
                spot_rt = math.sin(spot_ang / 2) * spot_hyp * spot_scale.x
                spot_up = math.sin(spot_ang / 2) * spot_hyp * spot_scale.y
                fw(f'"light_target" "0 0 -{spot_fw}"\n')
                fw(f'"light_right" "{spot_rt} 0 0"\n')
                fw(f'"light_up" "0 {spot_up} 0"\n')
                if "texture" not in keys:
                    fw(f'"texture" "lights/spot01"\n')
                spot_rot = obj.matrix_world.to_euler().to_matrix()
                d3_rot = [el for row in spot_rot.inverted_safe() for el in row]
                fw(f'"rotation" "{self.printvec(d3_rot)}"\n')
            elif self.option_brush == "Quake":
                spot_deg = math.degrees(spot_ang)
                spot_inner = spot_deg * (1 - obj.data.spot_blend)
                fw(f'"angle" "{spot_deg}"\n')  # Q1
                fw(f'"_softangle" "{spot_inner}"\n')  # Q1
                fw(f'"radius" "{math.tan(spot_ang/2) * 64}"\n')  # Q3
                self.seen_names.append(self.spot_name)
                spot_num = self.seen_names.count(self.spot_name)
                spot_rot = obj.matrix_world.to_euler().to_matrix()
                spot_org = spot_rot @ Vector((0, 0, -self.spot_offset)) + origin
                fw(f'"target" "{self.spot_name}{spot_num}"\n')
                fw("}\n{\n")
                fw(f'"classname" "{self.spot_class}"\n')
                fw(f'"origin" "{self.printvec(spot_org)}"\n')
                fw(f'"targetname" "{self.spot_name}{spot_num}"\n')
        fw("}\n")

    def process_empty(self, obj, fw):
        name = obj.name.rstrip("0123456789")
        name = name[:-1] if name[-1] in (".", " ") else obj.name
        fw('{\n"classname" "' + name + '"\n')
        origin = obj.matrix_world.to_translation() * self.option_scale
        fw(f'"origin" "{self.printvec(origin)}"\n')
        keys = obj.keys()
        if "angles" not in keys:
            if obj.type != "CAMERA":
                ang = obj.matrix_world.to_euler()
            else:
                ang = (obj.matrix_world @ self.cam_correct).to_euler()
            deg = (math.degrees(a) for a in (-ang.y, ang.z, ang.x))
            fw(f'"angles" "{self.printvec(deg)}"\n')
        for prop in keys:  # custom object properties
            if isinstance(obj[prop], (int, float, str)):  # no arrays
                fw(f'"{prop}" "{obj[prop]}"\n')
        fw("}\n")

    def execute(self, context):
        timer = time.time()
        map_text = []
        fw = map_text.append
        self.seen_names = []
        wspwn_objs, bmodel_objs = [], []
        patch_objs, light_objs, empty_objs = [], [], []

        if self.option_brush == "Doom3":
            fw("Version 2\n")
            template = ["{\nbrushDef3\n{\n", "}\n}\n"]
        elif self.option_uv == "BPrim":
            template = ["{\nbrushDef\n{\n", "}\n}\n"]
        else:
            template = ["{\n", "}\n"]
        fw('{\n"classname" "worldspawn"\n')
        if self.option_uv == "Valve":
            fw('"mapversion" "220"\n')

        # sort objects
        if self.option_sel:
            objects = context.selected_objects
        else:
            objects = context.scene.objects
        for obj in objects:
            if obj.type == "LIGHT" and self.option_lights != "None":
                light_objs.append(obj)
                continue
            elif obj.type in ("EMPTY", "CAMERA"):
                if self.option_empties != "None":
                    empty_objs.append(obj)
                    continue
            elif obj.type == "SURFACE":
                if self.option_nurbs in ("Def2", "Def3"):
                    patch_objs.append(obj)
                    continue
            elif obj.type == "META" and "." in obj.name:
                continue
            elif obj.type not in ("MESH", "SURFACE", "CURVE", "FONT", "META"):
                continue

            geo_type = obj.qmap_geo_type
            if geo_type == "Default":
                geo_type = self.option_geo
            if (
                (self.option_group == "None")
                or (
                    self.option_group == "Auto"
                    and geo_type == "Brush"
                    and obj.users_collection[0].name.startswith("worldspawn")
                )
                or (
                    self.option_group == "Auto"
                    and geo_type != "Brush"
                    and obj.name.startswith("worldspawn")
                )
            ):
                wspwn_objs.append(obj)
            else:
                bmodel_objs.append(obj)

        # process objects
        for obj in wspwn_objs:
            self.process_mesh(obj, fw, template)
        for obj in patch_objs:
            for spline in obj.data.splines:
                self.process_nurbs(obj, spline, fw)
        collections = [bpy.context.scene.collection] + bpy.data.collections[:]
        for col in collections:
            bmodel_brush_objs, bmodel_face_objs = [], []
            for obj in [ob for ob in col.objects if ob in bmodel_objs]:
                geo_type = obj.qmap_geo_type
                if geo_type == "Default":
                    geo_type = self.option_geo
                if geo_type == "Brush":
                    bmodel_brush_objs.append(obj)
                else:
                    bmodel_face_objs.append(obj)
            if bmodel_brush_objs:
                fw(self.entname(col))
                for obj in bmodel_brush_objs:
                    self.process_mesh(obj, fw, template)
            for obj in bmodel_face_objs:
                fw(self.entname(obj))
                self.process_mesh(obj, fw, template)
        fw("}\n")
        for obj in light_objs:
            self.process_light(obj, fw)
        for obj in empty_objs:
            self.process_empty(obj, fw)

        # handle output
        scene_str = "".join(map_text)
        if self.option_dest == "File":
            with open(self.filepath, "w") as file:
                file.write(scene_str)
        elif self.option_dest == "Clip":
            bpy.context.window_manager.clipboard = scene_str
        elif self.option_dest == "GTK":
            gtk_str = struct.pack("<Q", len(scene_str)) + scene_str.encode()
            if sys.platform.startswith("win"):
                clipid = u32.RegisterClipboardFormatW("RadiantClippings")
                handle = k32.GlobalAlloc(0x0042, len(gtk_str))
                pointer = k32.GlobalLock(handle)
                try:
                    k32.RtlCopyMemory(pointer, gtk_str, len(gtk_str))
                    u32.OpenClipboard(u32.GetActiveWindow())
                    u32.EmptyClipboard()
                    u32.SetClipboardData(clipid, handle)
                except:
                    self.report({"ERROR"}, "Failed to export GTK clipboard")
                finally:
                    k32.GlobalUnlock(pointer)
                    u32.CloseClipboard()
            else:
                self.report({"ERROR"}, "GTK export is currently Windows-only")
                bpy.context.window_manager.clipboard = scene_str

        timer = time.time() - timer
        self.report({"INFO"}, f"Finished exporting map, took {timer:g} sec")
        return {"FINISHED"}


def menu_func_export(self, context):
    self.layout.operator(ExportQuakeMap.bl_idname, text="Quake Map (.map)")


# 添加新的属性组类来存储选择的网格体和导出模式
class QMapMeshItem(bpy.types.PropertyGroup):
    mesh: PointerProperty(
        name="网格体",
        type=bpy.types.Object,
        description="要导出的网格对象",
        poll=lambda self, obj: obj.type == "MESH",
    )
    geo_type: EnumProperty(
        name="导出模式",
        items=ptxt["geo"]["items"],
        default=ptxt["geo"]["def"],
        description="此网格的导出模式",
    )
    soup_dir: EnumProperty(
        name="地形方向",
        items=ptxt["soup_dir"]["items"],
        default=ptxt["soup_dir"]["def"],
        description="此网格的地形挤压方向",
    )


# 添加操作类来添加/移除网格体
class QMAP_OT_AddSelectedMeshes(bpy.types.Operator):
    bl_idname = "qmap.add_selected_meshes"
    bl_label = "添加选中的网格体"
    bl_description = "将当前选中的网格体添加到导出列表"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        world = context.scene.world
        if not world:
            self.report({"ERROR"}, "场景没有世界设置")
            return {"CANCELLED"}

        added = 0
        for obj in context.selected_objects:
            if obj.type == "MESH":
                # 检查是否已经在列表中
                exists = False
                for item in world.qmap_meshes:
                    if item.mesh == obj:
                        exists = True
                        break

                if not exists:
                    item = world.qmap_meshes.add()
                    item.mesh = obj
                    # 使用全局设置作为默认值
                    item.geo_type = world.qmap_option_geo
                    item.soup_dir = world.qmap_option_soup_dir
                    added += 1

        self.report({"INFO"}, f"已添加 {added} 个网格体到导出列表")
        return {"FINISHED"}


class QMAP_OT_RemoveMesh(bpy.types.Operator):
    bl_idname = "qmap.remove_mesh"
    bl_label = "移除"
    bl_description = "从导出列表中移除此网格体"
    bl_options = {"REGISTER", "UNDO"}

    index: IntProperty()

    def execute(self, context):
        world = context.scene.world
        if not world:
            return {"CANCELLED"}

        if self.index >= 0 and self.index < len(world.qmap_meshes):
            world.qmap_meshes.remove(self.index)

        return {"FINISHED"}


class QMAP_OT_ClearMeshes(bpy.types.Operator):
    bl_idname = "qmap.clear_meshes"
    bl_label = "清空列表"
    bl_description = "清空导出网格体列表"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        world = context.scene.world
        if not world:
            return {"CANCELLED"}

        world.qmap_meshes.clear()
        return {"FINISHED"}


# 添加导出操作类
class QMAP_OT_ExportWorldMap(bpy.types.Operator):
    bl_idname = "qmap.export_world_map"
    bl_label = "导出Map地图"
    bl_description = "将选定的网格体导出为Quake Map格式"
    bl_options = {"REGISTER", "UNDO"}

    filepath: StringProperty(
        subtype="FILE_PATH",
    )
    filename_ext = ".map"

    def invoke(self, context, event):
        world = context.scene.world
        if not world or len(world.qmap_meshes) == 0:
            self.report({"ERROR"}, "没有选择要导出的网格体")
            return {"CANCELLED"}

        # 从world属性中获取输出设置
        dest_option = world.qmap_option_dest

        if dest_option == "File":
            context.window_manager.fileselect_add(self)
            return {"RUNNING_MODAL"}
        else:
            return self.execute(context)

    def execute(self, context):
        world = context.scene.world
        if not world or len(world.qmap_meshes) == 0:
            self.report({"ERROR"}, "没有选择要导出的网格体")
            return {"CANCELLED"}

        # 保存当前选择
        old_selection = context.selected_objects.copy()
        active_obj = context.active_object

        # 先将所有网格体的soup_dir存储到一个字典中
        soup_dirs = {}
        for item in world.qmap_meshes:
            if item.mesh and (
                item.geo_type == "Soup"
                or (item.geo_type == "Default" and world.qmap_option_geo == "Soup")
            ):
                soup_dirs[item.mesh.name] = item.soup_dir

        # 选择我们列表中的网格体
        bpy.ops.object.select_all(action="DESELECT")
        for item in world.qmap_meshes:
            if item.mesh:
                # 设置每个网格体的导出模式
                item.mesh.qmap_geo_type = item.geo_type
                # 为使用Soup模式的网格体或Default+全局Soup的网格体存储其特定的soup_dir
                if item.geo_type == "Soup" or (
                    item.geo_type == "Default" and world.qmap_option_geo == "Soup"
                ):
                    # 我们需要使用自定义属性来存储每个网格体的soup_dir
                    item.mesh["qmap_soup_dir"] = item.soup_dir
                item.mesh.select_set(True)

        # 准备导出参数
        export_args = {
            "filepath": self.filepath if world.qmap_option_dest == "File" else "",
            "option_sel": True,  # 现在我们已经选择了要导出的对象
            "option_tm": world.qmap_option_tm,
            "option_mod": world.qmap_option_mod,
            "option_tj": world.qmap_option_tj,
            "option_geo": world.qmap_option_geo,
            "option_grid": world.qmap_option_grid,
            "option_depth": world.qmap_option_depth,
            "option_scale": world.qmap_option_scale,
            "option_fp": world.qmap_option_fp,
            "option_brush": world.qmap_option_brush,
            "option_uv": world.qmap_option_uv,
            "option_flags": world.qmap_option_flags,
            "option_dest": world.qmap_option_dest,
            "option_group": world.qmap_option_group,
            "option_gname": world.qmap_option_gname,
            "option_skip": world.qmap_option_skip,
            "option_size": world.qmap_option_size,
            "option_soup_dir": world.qmap_option_soup_dir,
            "option_miter_method": world.qmap_option_miter_method,
            "option_lights": "None",
            "option_empties": "None",
            "option_nurbs": "None",
        }

        # 使用bpy.ops调用导出操作符
        bpy.ops.export.map("EXEC_DEFAULT", **export_args)

        # 清理临时自定义属性
        for obj in context.scene.objects:
            if "qmap_soup_dir" in obj:
                del obj["qmap_soup_dir"]

        # 恢复选择
        bpy.ops.object.select_all(action="DESELECT")
        for obj in old_selection:
            obj.select_set(True)
        if active_obj:
            context.view_layer.objects.active = active_obj

        return {"FINISHED"}


# 添加世界场景属性面板
class WORLD_PT_QMapExport(bpy.types.Panel):
    bl_label = "Map地图导出"
    bl_idname = "WORLD_PT_QMapExport"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "world"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        world = context.scene.world

        if not world:
            layout.label(text="请先创建世界设置", icon="ERROR")
            return

        # 添加网格体按钮
        row = layout.row()
        row.operator("qmap.add_selected_meshes", icon="PLUS")
        row.operator("qmap.clear_meshes", icon="X")

        # 网格体列表
        layout.label(text="导出网格体列表:")
        box = layout.box()

        if len(world.qmap_meshes) == 0:
            box.label(text="没有选择网格体", icon="INFO")
        else:
            for i, item in enumerate(world.qmap_meshes):
                row = box.row(align=True)
                if item.mesh:
                    row.label(text=item.mesh.name, icon="MESH_DATA")
                    row.prop(item, "geo_type", text="")
                    # 显示Soup方向选择器（当导出模式为Soup时，或者是Default且全局设置为Soup）
                    if item.geo_type == "Soup" or (
                        item.geo_type == "Default" and world.qmap_option_geo == "Soup"
                    ):
                        row.prop(item, "soup_dir", text="")
                    op = row.operator("qmap.remove_mesh", text="", icon="X")
                    op.index = i
                else:
                    row.label(text="缺失网格体", icon="ERROR")
                    op = row.operator("qmap.remove_mesh", text="", icon="X")
                    op.index = i

        # 导出设置
        layout.separator()
        row = layout.row()
        row.label(text="导出设置:", icon="SETTINGS")
        row.operator("qmap.save_preferences", icon="PRESET")

        col = layout.column(align=True)
        col.label(text="基本设置:")
        row = col.row()
        row.prop(world, "qmap_option_tm")
        row.prop(world, "qmap_option_mod")
        row.prop(world, "qmap_option_tj")

        col.separator()
        col.label(text="坐标设置:")
        row = col.row()
        row.prop(world, "qmap_option_grid")
        row.prop(world, "qmap_option_depth")
        row = col.row()
        row.prop(world, "qmap_option_scale")
        row.prop(world, "qmap_option_fp")

        col.separator()
        col.label(text="输出格式:")
        row = col.row()
        row.prop(world, "qmap_option_brush")
        row.prop(world, "qmap_option_uv")
        row = col.row()
        row.prop(world, "qmap_option_flags")
        row.prop(world, "qmap_option_dest")

        col.separator()
        col.label(text="其他设置:")
        col.prop(world, "qmap_option_geo")
        col.prop(world, "qmap_option_group")
        col.prop(world, "qmap_option_gname")
        col.prop(world, "qmap_option_skip")
        col.prop(world, "qmap_option_size")

        # 添加全局Soup方向设置（作为新网格体的默认值）
        col.separator()
        col.label(text="地形(Soup)默认设置:")
        col.prop(world, "qmap_option_soup_dir")
        col.label(text="外壳(Miter)默认设置:")
        col.prop(world, "qmap_option_miter_method")

        # 导出按钮
        layout.separator()
        layout.operator("qmap.export_world_map", icon="EXPORT")


# 添加保存偏好设置的操作符
class QMAP_OT_SavePreferences(bpy.types.Operator):
    bl_idname = "qmap.save_preferences"
    bl_label = "保存为默认设置"
    bl_description = "将当前设置保存为插件默认设置"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        world = context.scene.world
        if not world:
            self.report({"ERROR"}, "场景没有世界设置")
            return {"CANCELLED"}

        prefs = _export_prefs()
        if prefs is _EXPORT_DEFAULTS:
            self.report({"WARNING"}, "整合模式下没有独立导出默认设置，当前场景设置仍然保留")
            return {"CANCELLED"}

        # 将当前世界属性设置保存到偏好设置
        prefs.tm = world.qmap_option_tm
        prefs.mod = world.qmap_option_mod
        prefs.tj = world.qmap_option_tj
        prefs.geo = world.qmap_option_geo
        prefs.grid = world.qmap_option_grid
        prefs.depth = world.qmap_option_depth
        prefs.scale = world.qmap_option_scale
        prefs.fp = world.qmap_option_fp
        prefs.brush = world.qmap_option_brush
        prefs.uv = world.qmap_option_uv
        prefs.flags = world.qmap_option_flags
        prefs.dest = world.qmap_option_dest
        prefs.group = world.qmap_option_group
        prefs.gname = world.qmap_option_gname
        prefs.skip = world.qmap_option_skip
        prefs.size = world.qmap_option_size
        prefs.soup_dir = world.qmap_option_soup_dir
        prefs.miter_method = world.qmap_option_miter_method

        self.report({"INFO"}, "已保存设置为默认值")
        return {"FINISHED"}


# 在register函数中注册新的类和属性
def register():
    bpy.utils.register_class(ExportQuakeMap)
    bpy.types.Object.qmap_geo_type = bpy.props.EnumProperty(
        name="Geo",
        items=(("Default", "Default", "No override"),) + ptxt["geo"]["items"],
        description="Mesh export mode override",
    )
    bpy.utils.register_class(ExportQuakeMapObjectPanel)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

    # 注册新的类
    bpy.utils.register_class(QMapMeshItem)
    bpy.utils.register_class(QMAP_OT_AddSelectedMeshes)
    bpy.utils.register_class(QMAP_OT_RemoveMesh)
    bpy.utils.register_class(QMAP_OT_ClearMeshes)
    bpy.utils.register_class(QMAP_OT_ExportWorldMap)
    bpy.utils.register_class(QMAP_OT_SavePreferences)
    bpy.utils.register_class(WORLD_PT_QMapExport)

    # 添加世界属性
    bpy.types.World.qmap_meshes = CollectionProperty(type=QMapMeshItem)

    prefs = _export_prefs()

    # 添加导出选项属性，使用偏好设置中的默认值
    bpy.types.World.qmap_option_tm = BoolProperty(
        name=ptxt["tm"]["name"],
        default=prefs.tm,
        description=ptxt["tm"]["desc"],
    )
    bpy.types.World.qmap_option_mod = BoolProperty(
        name=ptxt["mod"]["name"],
        default=prefs.mod,
        description=ptxt["mod"]["desc"],
    )
    bpy.types.World.qmap_option_tj = BoolProperty(
        name=ptxt["tj"]["name"],
        default=prefs.tj,
        description=ptxt["tj"]["desc"],
    )
    bpy.types.World.qmap_option_geo = EnumProperty(
        name=ptxt["geo"]["name"],
        default=prefs.geo,
        items=ptxt["geo"]["items"],
    )
    bpy.types.World.qmap_option_grid = FloatProperty(
        name=ptxt["grid"]["name"],
        min=0,
        default=prefs.grid,
        description=ptxt["grid"]["desc"],
    )
    bpy.types.World.qmap_option_depth = FloatProperty(
        name=ptxt["depth"]["name"],
        default=prefs.depth,
        description=ptxt["depth"]["desc"],
    )
    bpy.types.World.qmap_option_scale = FloatProperty(
        name=ptxt["scale"]["name"],
        default=prefs.scale,
        description=ptxt["scale"]["desc"],
    )
    bpy.types.World.qmap_option_fp = IntProperty(
        name=ptxt["fp"]["name"],
        min=0,
        soft_max=17,
        default=prefs.fp,
        description=ptxt["fp"]["desc"],
    )
    bpy.types.World.qmap_option_brush = EnumProperty(
        name=ptxt["brush"]["name"],
        default=prefs.brush,
        items=ptxt["brush"]["items"],
    )
    bpy.types.World.qmap_option_uv = EnumProperty(
        name=ptxt["uv"]["name"],
        default=prefs.uv,
        items=ptxt["uv"]["items"],
    )
    bpy.types.World.qmap_option_flags = EnumProperty(
        name=ptxt["flags"]["name"],
        default=prefs.flags,
        items=ptxt["flags"]["items"],
    )
    bpy.types.World.qmap_option_dest = EnumProperty(
        name=ptxt["dest"]["name"],
        default=prefs.dest,
        items=ptxt["dest"]["items"],
    )
    bpy.types.World.qmap_option_group = EnumProperty(
        name=ptxt["group"]["name"],
        default=prefs.group,
        items=ptxt["group"]["items"],
    )
    bpy.types.World.qmap_option_gname = StringProperty(
        name=ptxt["gname"]["name"],
        default=prefs.gname,
        description=ptxt["gname"]["desc"],
    )
    bpy.types.World.qmap_option_skip = StringProperty(
        name=ptxt["skip"]["name"],
        default=prefs.skip,
        description=ptxt["skip"]["desc"],
    )
    bpy.types.World.qmap_option_size = EnumProperty(
        name=ptxt["size"]["name"],
        default=prefs.size,
        items=ptxt["size"]["items"],
        description=ptxt["size"]["desc"],
    )
    bpy.types.World.qmap_option_soup_dir = EnumProperty(
        name=ptxt["soup_dir"]["name"],
        default=prefs.soup_dir,
        items=ptxt["soup_dir"]["items"],
        description="新网格体的默认地形方向",
    )
    bpy.types.World.qmap_option_miter_method = EnumProperty(
        name=ptxt["miter_method"]["name"],
        default=prefs.miter_method,
        items=ptxt["miter_method"]["items"],
        description=ptxt["miter_method"]["desc"],
    )


def unregister():
    bpy.utils.unregister_class(ExportQuakeMap)
    del bpy.types.Object.qmap_geo_type
    bpy.utils.unregister_class(ExportQuakeMapObjectPanel)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)

    # 注销新的类
    bpy.utils.unregister_class(WORLD_PT_QMapExport)
    bpy.utils.unregister_class(QMAP_OT_ExportWorldMap)
    bpy.utils.unregister_class(QMAP_OT_SavePreferences)
    bpy.utils.unregister_class(QMAP_OT_ClearMeshes)
    bpy.utils.unregister_class(QMAP_OT_RemoveMesh)
    bpy.utils.unregister_class(QMAP_OT_AddSelectedMeshes)
    bpy.utils.unregister_class(QMapMeshItem)

    # 删除世界属性
    del bpy.types.World.qmap_meshes
    del bpy.types.World.qmap_option_tm
    del bpy.types.World.qmap_option_mod
    del bpy.types.World.qmap_option_tj
    del bpy.types.World.qmap_option_geo
    del bpy.types.World.qmap_option_grid
    del bpy.types.World.qmap_option_depth
    del bpy.types.World.qmap_option_scale
    del bpy.types.World.qmap_option_fp
    del bpy.types.World.qmap_option_brush
    del bpy.types.World.qmap_option_uv
    del bpy.types.World.qmap_option_flags
    del bpy.types.World.qmap_option_dest
    del bpy.types.World.qmap_option_group
    del bpy.types.World.qmap_option_gname
    del bpy.types.World.qmap_option_skip
    del bpy.types.World.qmap_option_size
    del bpy.types.World.qmap_option_soup_dir
    del bpy.types.World.qmap_option_miter_method
