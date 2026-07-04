import bpy
import os


def addon_dir():
    """获取插件目录路径"""
    return os.path.dirname(os.path.abspath(__file__))


def abspath(path: str) -> str:
    """获取绝对路径"""
    if not path:
        return path
    try:
        return bpy.path.abspath(path)
    except Exception:
        return path


def ensure_dir(path: str):
    """确保目录存在"""
    if path and not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


def report_error(operator, msg: str):
    """报告错误信息"""
    operator.report({"ERROR"}, msg)


def get_prefs(context):
    """获取插件首选项"""
    return context.preferences.addons[__name__.split('.')[0]].preferences
