import bpy
import os
import datetime
import itertools
import math
import re
from bpy.types import Operator
from bpy.props import StringProperty
from mathutils import Matrix, Vector
from ..utils import abspath, ensure_dir, report_error, addon_dir, get_prefs
from .wad_import import WAD3Loader


PROP_RE = re.compile(r'^"([^"]*)"\s+"([^"]*)"')
FACE_RE = re.compile(
    r"^\(\s*([^)]+?)\s*\)\s*\(\s*([^)]+?)\s*\)\s*\(\s*([^)]+?)\s*\)\s+(\S+)(.*)$"
)
TEX_AXIS_RE = re.compile(
    r"\[\s*([^\]]+)\s*\]\s*\[\s*([^\]]+)\s*\]\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)"
)
EPS = 1e-4


def _parse_vec(text):
    parts = [float(part) for part in text.split()]
    if len(parts) != 3:
        raise ValueError(f"invalid vector: {text}")
    return Vector(parts)


def _parse_tex_axis(text):
    parts = [float(part) for part in text.split()]
    if len(parts) != 4:
        return None
    return Vector(parts[:3]), parts[3]


def _parse_face_texture_info(text):
    match = TEX_AXIS_RE.search(text)
    if not match:
        return {
            "tex_axes": None,
            "rotation": 0.0,
            "x_scale": 1.0,
            "y_scale": 1.0,
        }

    u_axis = _parse_tex_axis(match.group(1))
    v_axis = _parse_tex_axis(match.group(2))
    if u_axis is None or v_axis is None:
        return {
            "tex_axes": None,
            "rotation": 0.0,
            "x_scale": 1.0,
            "y_scale": 1.0,
        }

    x_scale = float(match.group(4))
    y_scale = float(match.group(5))
    return {
        "tex_axes": (u_axis, v_axis),
        "rotation": float(match.group(3)),
        "x_scale": x_scale if abs(x_scale) > EPS else 1.0,
        "y_scale": y_scale if abs(y_scale) > EPS else 1.0,
    }


def _parse_map(path):
    entities = []
    entity = None
    brush = None
    depth = 0

    with open(path, "r", encoding="utf-8", errors="replace") as file:
        for raw_line in file:
            line = raw_line.strip()
            if not line or line.startswith("//"):
                continue

            if line == "{":
                if depth == 0:
                    entity = {"properties": {}, "brushes": []}
                elif depth == 1:
                    brush = []
                depth += 1
                continue

            if line == "}":
                depth -= 1
                if depth == 1 and entity is not None and brush is not None:
                    entity["brushes"].append(brush)
                    brush = None
                elif depth == 0 and entity is not None:
                    entities.append(entity)
                    entity = None
                continue

            if depth == 1 and entity is not None:
                match = PROP_RE.match(line)
                if match:
                    entity["properties"][match.group(1)] = match.group(2)
            elif depth == 2 and brush is not None:
                match = FACE_RE.match(line)
                if match:
                    texture_info = _parse_face_texture_info(match.group(5))
                    brush.append(
                        {
                            "points": [_parse_vec(match.group(i)) for i in range(1, 4)],
                            "texture": match.group(4),
                            **texture_info,
                        }
                    )

    return entities


def _plane_from_face(face, center=None):
    p0, p1, p2 = face["points"]
    normal = (p2 - p0).cross(p1 - p0)
    if normal.length <= EPS:
        return None
    normal.normalize()
    return normal, -normal.dot(p0)


def _intersect_planes(a, b, c):
    matrix = Matrix(
        (
            (a[0].x, a[0].y, a[0].z),
            (b[0].x, b[0].y, b[0].z),
            (c[0].x, c[0].y, c[0].z),
        )
    )
    if abs(matrix.determinant()) <= EPS:
        return None
    return matrix.inverted() @ Vector((-a[1], -b[1], -c[1]))


def _sort_face_vertices(points, normal):
    center = sum(points, Vector()) / len(points)
    axis_u = points[0] - center
    if axis_u.length <= EPS:
        return points
    axis_u.normalize()
    axis_v = normal.cross(axis_u)
    if axis_v.length <= EPS:
        return points
    axis_v.normalize()
    return sorted(
        points,
        key=lambda point: math.atan2((point - center).dot(axis_v), (point - center).dot(axis_u)),
    )


def _brush_to_mesh(brush):
    all_points = [point for face in brush for point in face["points"]]
    if len(all_points) < 12:
        return None

    planes = []
    for face in brush:
        plane = _plane_from_face(face)
        if plane is not None:
            planes.append((face, plane))

    vertices = []
    vertex_by_key = {}
    for (_, plane_a), (_, plane_b), (_, plane_c) in itertools.combinations(planes, 3):
        point = _intersect_planes(plane_a, plane_b, plane_c)
        if point is None:
            continue
        if all(normal.dot(point) + dist <= 0.01 for _, (normal, dist) in planes):
            key = tuple(round(coord, 3) for coord in point)
            if key not in vertex_by_key:
                vertex_by_key[key] = len(vertices)
                vertices.append(point)

    faces = []
    face_sources = []
    for source_face, (normal, dist) in planes:
        face_points = [
            point for point in vertices if abs(normal.dot(point) + dist) <= 0.01
        ]
        if len(face_points) < 3:
            continue
        sorted_points = _sort_face_vertices(face_points, normal)
        faces.append([vertex_by_key[tuple(round(coord, 3) for coord in point)] for point in sorted_points])
        face_sources.append(source_face)

    if len(vertices) < 4 or len(faces) < 4:
        return None
    return vertices, faces, face_sources


def _get_child_collection(parent, name):
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
    if collection.name not in parent.children:
        parent.children.link(collection)
    return collection


def _material(name):
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name)
    return material


def _material_with_image(name, image):
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name)

    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()

    output_node = nodes.new("ShaderNodeOutputMaterial")
    bsdf_node = nodes.new("ShaderNodeBsdfPrincipled")
    tex_node = nodes.new("ShaderNodeTexImage")
    tex_node.image = image
    tex_node.interpolation = "Linear"
    tex_node.extension = "REPEAT"

    links = material.node_tree.links
    links.new(tex_node.outputs["Color"], bsdf_node.inputs["Base Color"])
    if name.startswith("{"):
        links.new(tex_node.outputs["Alpha"], bsdf_node.inputs["Alpha"])
        material.blend_method = "BLEND"
    links.new(bsdf_node.outputs["BSDF"], output_node.inputs["Surface"])
    return material


def _create_wad_image(image_data, texture_name):
    name = image_data["name"]
    width = image_data["width"]
    height = image_data["height"]
    pixels = image_data["pixels"]
    palette = image_data["palette"]
    transparent = texture_name.startswith("{")

    existing = bpy.data.images.get(name)
    if existing is not None and tuple(existing.size) == (width, height):
        return existing

    image = bpy.data.images.new(name, width, height, alpha=True)
    rgba_pixels = []
    for pixel_index in pixels:
        if pixel_index < len(palette):
            r, g, b, _ = palette[pixel_index]
            alpha = 0.0 if transparent and pixel_index == 255 else 1.0
            rgba_pixels.extend((r, g, b, alpha))
        else:
            rgba_pixels.extend((0.0, 0.0, 0.0, 1.0))

    image.pixels = rgba_pixels
    image.pack()
    return image


def _used_textures(entities):
    return {
        face["texture"].lower(): face["texture"]
        for entity in entities
        for brush in entity["brushes"]
        for face in brush
        if face.get("texture")
    }


def _wad_paths(entities, map_path):
    wad_value = ""
    for entity in entities:
        if entity["properties"].get("classname", "worldspawn") == "worldspawn":
            wad_value = entity["properties"].get("wad", "")
            break

    map_dir = os.path.dirname(map_path)
    paths = []
    for raw_path in wad_value.split(";"):
        raw_path = raw_path.strip().strip('"')
        if not raw_path:
            continue
        path = raw_path
        if not os.path.isabs(path):
            path = os.path.join(map_dir, path)
        paths.append(os.path.normpath(path))
    return paths


def _load_wad_materials(entities, map_path, operator):
    used_textures = _used_textures(entities)
    pending = set(used_textures.keys())
    texture_sizes = {}
    material_names = {}
    loaded_count = 0
    missing_wads = 0

    for wad_path in _wad_paths(entities, map_path):
        if not pending:
            break
        if not os.path.isfile(wad_path):
            missing_wads += 1
            continue

        loader = WAD3Loader()
        try:
            loader.load_file(wad_path)
            lump_by_name = {
                lump["name"].lower(): (index, lump["name"])
                for index, lump in enumerate(loader.lumps_info)
            }
            for texture_key in list(pending):
                if texture_key not in lump_by_name:
                    continue
                index, texture_name = lump_by_name[texture_key]
                image_data = loader.get_lump_image_data(index)
                material_name = used_textures[texture_key]
                image = _create_wad_image(image_data, material_name)
                _material_with_image(material_name, image)
                texture_sizes[texture_key] = (image_data["width"], image_data["height"])
                material_names[texture_key] = material_name
                pending.remove(texture_key)
                loaded_count += 1
        except Exception as error:
            operator.report({"WARNING"}, f"跳过 WAD {wad_path}: {error}")
        finally:
            loader.close()

    if missing_wads:
        operator.report({"WARNING"}, f"有 {missing_wads} 个 WAD 路径不存在，已跳过")
    return texture_sizes, material_names, loaded_count, len(pending)


def _transform_matrix(prefs):
    return Matrix.Diagonal((prefs.scale, prefs.scale, prefs.scale, 1.0))


def _fallback_uv_axes(normal):
    axis_u = Vector((1.0, 0.0, 0.0))
    if abs(normal.dot(axis_u)) > 0.95:
        axis_u = Vector((0.0, 1.0, 0.0))
    axis_u = axis_u - normal * normal.dot(axis_u)
    if axis_u.length <= EPS:
        axis_u = Vector((0.0, 0.0, 1.0))
    axis_u.normalize()
    axis_v = normal.cross(axis_u)
    axis_v.normalize()
    return (axis_u, 0.0), (axis_v, 0.0)


def _assign_uvs(mesh, vertices, face_sources, texture_sizes, default_size):
    uv_layer = mesh.uv_layers.new(name="UVMap")
    for polygon, source_face in zip(mesh.polygons, face_sources):
        texture_key = source_face["texture"].lower()
        width, height = texture_sizes.get(texture_key, (default_size, default_size))
        tex_axes = source_face.get("tex_axes")
        if tex_axes is None:
            normal = polygon.normal.copy()
            u_axis, v_axis = _fallback_uv_axes(normal)
        else:
            u_axis, v_axis = tex_axes

        x_scale = source_face.get("x_scale", 1.0)
        y_scale = source_face.get("y_scale", 1.0)
        for loop_index in polygon.loop_indices:
            vertex = vertices[mesh.loops[loop_index].vertex_index]
            u = (vertex.dot(u_axis[0]) / x_scale + u_axis[1]) / width
            v = (vertex.dot(v_axis[0]) / y_scale + v_axis[1]) / height
            uv_layer.data[loop_index].uv = (u, 1.0 - v)


def _texture_material(texture, material_names):
    return _material(material_names.get(texture.lower(), texture))


def import_map_direct(operator, context, filepath):
    prefs = get_prefs(context)
    entities = _parse_map(filepath)
    if not entities:
        report_error(operator, "MAP 中没有可导入实体")
        return {"CANCELLED"}

    for obj in list(context.scene.objects):
        if obj.name == "Cube" and obj.type == "MESH" and len(obj.data.polygons) == 6:
            bpy.data.objects.remove(obj, do_unlink=True)

    basename = os.path.splitext(os.path.basename(filepath))[0]
    root = bpy.data.collections.new(f"MAP_{basename}")
    context.scene.collection.children.link(root)
    transform = _transform_matrix(prefs)
    texture_sizes, material_names, loaded_materials, missing_materials = _load_wad_materials(
        entities, filepath, operator
    )

    imported = 0
    skipped = 0
    for entity_index, entity in enumerate(entities):
        classname = entity["properties"].get("classname", "worldspawn")
        entity_root = _get_child_collection(root, classname)
        target_collection = entity_root
        if classname != "worldspawn":
            target_collection = _get_child_collection(entity_root, f"{classname}{entity_index}")

        for brush_index, brush in enumerate(entity["brushes"]):
            result = _brush_to_mesh(brush)
            if result is None:
                skipped += 1
                continue

            vertices, faces, face_sources = result
            mesh = bpy.data.meshes.new(f"{classname}{entity_index}_b{brush_index}")
            transformed_vertices = [
                (transform @ vertex.to_4d()).to_3d() for vertex in vertices
            ]
            mesh.from_pydata(transformed_vertices, [], faces)
            mesh.update(calc_edges=True)
            _assign_uvs(
                mesh,
                vertices,
                face_sources,
                texture_sizes,
                prefs.default_tex_size,
            )

            material_indices = {}
            for texture in [face["texture"] for face in face_sources]:
                if texture not in material_indices:
                    material_indices[texture] = len(mesh.materials)
                    mesh.materials.append(_texture_material(texture, material_names))
            for polygon, source_face in zip(mesh.polygons, face_sources):
                texture = source_face["texture"]
                polygon.material_index = material_indices[texture]

            obj = bpy.data.objects.new(mesh.name, mesh)
            target_collection.objects.link(obj)
            imported += 1

    operator.report(
        {"INFO"},
        f"直接导入 MAP 完成: {imported} brushes, skipped {skipped}, "
        f"WAD materials {loaded_materials}, missing {missing_materials}",
    )
    return {"FINISHED"}


class GOLDSRC_OT_ImportFromFile(Operator):
    bl_idname = "goldsrc.import_from_file"
    bl_label = "直接导入 MAP 文件"
    bl_options = {"REGISTER", "UNDO"}

    filepath: StringProperty(subtype="FILE_PATH")

    def execute(self, context):
        path = abspath(self.filepath)
        if not path or not os.path.isfile(path):
            report_error(self, "请选择有效的 .map 文件")
            return {"CANCELLED"}
        return import_map_direct(self, context, path)

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class GOLDSRC_OT_ImportFromClipboard(Operator):
    bl_idname = "goldsrc.import_from_clipboard"
    bl_label = "从剪贴板直接导入 MAP"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        text = (
            bpy.context.window_manager.clipboard if bpy.context.window_manager else ""
        )
        if not text or len(text.strip()) == 0:
            report_error(self, "剪贴板为空或无效")
            return {"CANCELLED"}

        tempdir = bpy.app.tempdir or os.path.join(addon_dir(), "_tmp")
        ensure_dir(tempdir)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        tmp_map = os.path.join(tempdir, f"clipboard_{stamp}.map")
        try:
            with open(tmp_map, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception as e:
            report_error(self, f"写入临时 MAP 失败: {e}")
            return {"CANCELLED"}

        return import_map_direct(self, context, tmp_map)
