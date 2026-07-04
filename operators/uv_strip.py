import bpy
import bmesh
from bpy.types import Operator
from mathutils import Vector


def _selected_quad_records(context):
    records = []
    skipped = 0
    for obj in context.objects_in_mode_unique_data:
        if obj.type != "MESH":
            continue
        bm = bmesh.from_edit_mesh(obj.data)
        uv_layer = bm.loops.layers.uv.verify()
        bm.faces.ensure_lookup_table()
        for face in bm.faces:
            if not face.select:
                continue
            if len(face.verts) != 4:
                skipped += 1
                continue
            world_verts = [obj.matrix_world @ vert.co for vert in face.verts]
            center = sum(world_verts, Vector()) / 4.0
            records.append((obj, bm, uv_layer, face, world_verts, center))
    return records, skipped


def _order_records(records):
    if len(records) <= 2:
        return records

    endpoints = max(
        ((a, b) for a in range(len(records)) for b in range(len(records)) if a != b),
        key=lambda pair: (records[pair[0]][5] - records[pair[1]][5]).length,
    )
    ordered = [records[endpoints[0]]]
    remaining = set(range(len(records)))
    remaining.remove(endpoints[0])
    while remaining:
        current = ordered[-1][5]
        next_index = min(remaining, key=lambda index: (records[index][5] - current).length)
        ordered.append(records[next_index])
        remaining.remove(next_index)
    return ordered


def _safe_normalize(vector, fallback):
    if vector.length <= 1e-6:
        return fallback.copy()
    result = vector.copy()
    result.normalize()
    return result


def _face_u_bounds(ordered, center_us, index, tangent, scale):
    if len(ordered) == 1:
        center = ordered[index][5]
        tangent = _safe_normalize(tangent, Vector((1, 0, 0)))
        half_width = max(abs((vert - center).dot(tangent)) for vert in ordered[index][4]) * scale
        return -half_width, half_width

    if index == 0:
        half_step = (center_us[1] - center_us[0]) / 2.0
        u_left = center_us[0] - half_step
    else:
        u_left = (center_us[index - 1] + center_us[index]) / 2.0

    if index == len(ordered) - 1:
        half_step = (center_us[index] - center_us[index - 1]) / 2.0
        u_right = center_us[index] + half_step
    else:
        u_right = (center_us[index] + center_us[index + 1]) / 2.0

    return u_left, u_right


def _face_half_height(verts, tangent, scale):
    center = sum(verts, Vector()) / 4.0
    normal = _safe_normalize((verts[1] - verts[0]).cross(verts[2] - verts[0]), Vector((0, 0, 1)))
    tangent = _safe_normalize(tangent, Vector((1, 0, 0)))
    side_axis = _safe_normalize(normal.cross(tangent), Vector((0, 1, 0)))
    return max(abs((vert - center).dot(side_axis)) for vert in verts) * scale


def _assign_face_uv(face, uv_layer, verts, center, tangent, u_left, u_right, half_height):
    center = sum(verts, Vector()) / 4.0
    normal = _safe_normalize((verts[1] - verts[0]).cross(verts[2] - verts[0]), Vector((0, 0, 1)))
    tangent = _safe_normalize(tangent, Vector((1, 0, 0)))
    side_axis = _safe_normalize(normal.cross(tangent), Vector((0, 1, 0)))
    columns = sorted(
        ((index, (vert - center).dot(tangent), (vert - center).dot(side_axis)) for index, vert in enumerate(verts)),
        key=lambda item: item[1],
    )
    left = sorted(columns[:2], key=lambda item: item[2])
    right = sorted(columns[2:], key=lambda item: item[2])
    uv_by_loop = {
        left[0][0]: (u_left, -half_height),
        left[1][0]: (u_left, half_height),
        right[0][0]: (u_right, -half_height),
        right[1][0]: (u_right, half_height),
    }

    for index, loop in enumerate(face.loops):
        loop[uv_layer].uv = uv_by_loop[index]


class GOLDSRC_OT_UnwrapSelectedQuadStrip(Operator):
    bl_idname = "goldsrc.unwrap_selected_quad_strip"
    bl_label = "按选中四边面展开UV"
    bl_description = "按选中四边面的几何顺序生成连续带状UV，不依赖拓扑连通"
    bl_options = {"REGISTER", "UNDO"}

    uv_scale: bpy.props.FloatProperty(
        name="UV Scale",
        default=0.01,
        min=0.0001,
        description="世界距离到UV坐标的缩放",
    )

    @classmethod
    def poll(cls, context):
        return context.mode == "EDIT_MESH"

    def execute(self, context):
        records, skipped = _selected_quad_records(context)
        if not records:
            self.report({"ERROR"}, "请选择至少一个四边面")
            return {"CANCELLED"}

        ordered = _order_records(records)

        center_us = []
        u = 0.0
        previous_center = None
        touched = set()
        uv_data = []
        half_height = 0.0
        for record in ordered:
            center = record[5]
            if previous_center is not None:
                u += (center - previous_center).length * self.uv_scale
            center_us.append(u)
            previous_center = center

        for index, record in enumerate(ordered):
            obj, bm, uv_layer, face, verts, center = record
            if len(ordered) == 1:
                tangent = verts[1] - verts[0]
            elif index == 0:
                tangent = ordered[1][5] - center
            elif index == len(ordered) - 1:
                tangent = center - ordered[index - 1][5]
            else:
                tangent = ordered[index + 1][5] - ordered[index - 1][5]
            previous_center = center
            u_left, u_right = _face_u_bounds(ordered, center_us, index, tangent, self.uv_scale)
            half_height = max(half_height, _face_half_height(verts, tangent, self.uv_scale))
            uv_data.append((face, uv_layer, verts, center, tangent, u_left, u_right))
            touched.add(obj)

        for face, uv_layer, verts, center, tangent, u_left, u_right in uv_data:
            _assign_face_uv(face, uv_layer, verts, center, tangent, u_left, u_right, half_height)

        for obj in touched:
            bmesh.update_edit_mesh(obj.data)

        message = f"已展开 {len(records)} 个四边面"
        if skipped:
            message += f"，跳过 {skipped} 个非四边面"
        self.report({"INFO"}, message)
        return {"FINISHED"}
