import bpy
from bpy.types import AddonPreferences
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty

from . import export_map


EXPORT_TEXT = export_map.ptxt


class GOLDSRC_AddonPreferences(AddonPreferences):
    bl_idname = __name__.split('.')[0]

    scale: FloatProperty(name="Scale", default=0.01)
    default_tex_size: IntProperty(name="默认贴图尺寸", default=256, min=1)

    export_sel: BoolProperty(
        name=EXPORT_TEXT["sel"]["name"],
        default=EXPORT_TEXT["sel"]["def"],
        description=EXPORT_TEXT["sel"]["desc"],
    )
    export_tm: BoolProperty(
        name=EXPORT_TEXT["tm"]["name"],
        default=EXPORT_TEXT["tm"]["def"],
        description=EXPORT_TEXT["tm"]["desc"],
    )
    export_mod: BoolProperty(
        name=EXPORT_TEXT["mod"]["name"],
        default=EXPORT_TEXT["mod"]["def"],
        description=EXPORT_TEXT["mod"]["desc"],
    )
    export_tj: BoolProperty(
        name=EXPORT_TEXT["tj"]["name"],
        default=EXPORT_TEXT["tj"]["def"],
        description=EXPORT_TEXT["tj"]["desc"],
    )
    export_geo: EnumProperty(
        name=EXPORT_TEXT["geo"]["name"],
        default=EXPORT_TEXT["geo"]["def"],
        items=EXPORT_TEXT["geo"]["items"],
    )
    export_nurbs: EnumProperty(
        name=EXPORT_TEXT["nurbs"]["name"],
        default=EXPORT_TEXT["nurbs"]["def"],
        items=EXPORT_TEXT["nurbs"]["items"],
    )
    export_lights: EnumProperty(
        name=EXPORT_TEXT["lights"]["name"],
        default=EXPORT_TEXT["lights"]["def"],
        items=EXPORT_TEXT["lights"]["items"],
    )
    export_empties: EnumProperty(
        name=EXPORT_TEXT["empties"]["name"],
        default=EXPORT_TEXT["empties"]["def"],
        items=EXPORT_TEXT["empties"]["items"],
    )
    export_grid: FloatProperty(
        name=EXPORT_TEXT["grid"]["name"],
        min=0,
        default=EXPORT_TEXT["grid"]["def"],
        description=EXPORT_TEXT["grid"]["desc"],
    )
    export_depth: FloatProperty(
        name=EXPORT_TEXT["depth"]["name"],
        default=EXPORT_TEXT["depth"]["def"],
        description=EXPORT_TEXT["depth"]["desc"],
    )
    export_scale: FloatProperty(
        name=EXPORT_TEXT["scale"]["name"],
        default=EXPORT_TEXT["scale"]["def"],
        description=EXPORT_TEXT["scale"]["desc"],
    )
    export_fp: IntProperty(
        name=EXPORT_TEXT["fp"]["name"],
        min=0,
        soft_max=17,
        default=EXPORT_TEXT["fp"]["def"],
        description=EXPORT_TEXT["fp"]["desc"],
    )
    export_brush: EnumProperty(
        name=EXPORT_TEXT["brush"]["name"],
        default=EXPORT_TEXT["brush"]["def"],
        items=EXPORT_TEXT["brush"]["items"],
    )
    export_uv: EnumProperty(
        name=EXPORT_TEXT["uv"]["name"],
        default=EXPORT_TEXT["uv"]["def"],
        items=EXPORT_TEXT["uv"]["items"],
    )
    export_flags: EnumProperty(
        name=EXPORT_TEXT["flags"]["name"],
        default=EXPORT_TEXT["flags"]["def"],
        items=EXPORT_TEXT["flags"]["items"],
    )
    export_dest: EnumProperty(
        name=EXPORT_TEXT["dest"]["name"],
        default=EXPORT_TEXT["dest"]["def"],
        items=EXPORT_TEXT["dest"]["items"],
    )
    export_group: EnumProperty(
        name=EXPORT_TEXT["group"]["name"],
        default=EXPORT_TEXT["group"]["def"],
        items=EXPORT_TEXT["group"]["items"],
    )
    export_gname: StringProperty(
        name=EXPORT_TEXT["gname"]["name"],
        default=EXPORT_TEXT["gname"]["def"],
        description=EXPORT_TEXT["gname"]["desc"],
    )
    export_skip: StringProperty(
        name=EXPORT_TEXT["skip"]["name"],
        default=EXPORT_TEXT["skip"]["def"],
        description=EXPORT_TEXT["skip"]["desc"],
    )
    export_size: EnumProperty(
        name=EXPORT_TEXT["size"]["name"],
        default=EXPORT_TEXT["size"]["def"],
        items=EXPORT_TEXT["size"]["items"],
        description=EXPORT_TEXT["size"]["desc"],
    )
    export_soup_dir: EnumProperty(
        name=EXPORT_TEXT["soup_dir"]["name"],
        default=EXPORT_TEXT["soup_dir"]["def"],
        items=EXPORT_TEXT["soup_dir"]["items"],
        description=EXPORT_TEXT["soup_dir"]["desc"],
    )
    export_miter_method: EnumProperty(
        name=EXPORT_TEXT["miter_method"]["name"],
        default=EXPORT_TEXT["miter_method"]["def"],
        items=EXPORT_TEXT["miter_method"]["items"],
        description=EXPORT_TEXT["miter_method"]["desc"],
    )
    
    # 面选择功能的参数
    perpendicular_angle_threshold: FloatProperty(
        name="垂直角度阈值",
        description="与Z轴垂直的角度阈值（度）",
        default=5.0,
        min=0.1,
        max=45.0
    )

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.label(text="MAP 直导参数：")
        grid = col.grid_flow(columns=2, align=True)
        grid.prop(self, "scale")
        grid.prop(self, "default_tex_size")
        col.separator()
        col.label(text="面选择功能：")
        col.prop(self, "perpendicular_angle_threshold")
        col.separator()
        col.label(text="MAP 导出默认设置：")
        grid = col.grid_flow(columns=2, align=True)
        for prop in (
            "export_geo",
            "export_brush",
            "export_uv",
            "export_dest",
            "export_grid",
            "export_depth",
            "export_scale",
            "export_fp",
            "export_group",
            "export_gname",
            "export_skip",
            "export_size",
            "export_soup_dir",
            "export_miter_method",
        ):
            grid.prop(self, prop)
        col.separator()
        row = col.row(align=True)
        for prop in ("export_sel", "export_tm", "export_mod", "export_tj"):
            row.prop(self, prop)
