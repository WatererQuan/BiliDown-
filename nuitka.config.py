# nuitka.config.py

from nuitka.plugins.PluginBase import NuitkaPluginBase

class NuitkaQtPlugin(NuitkaPluginBase):
    plugin_name = "qt-plugin"

    @staticmethod
    def createPreModuleLoadCode(module):
        if module.getFullName() == "__main__":
            return """
import os

# 设置Qt插件路径
qt_plugin_path = os.path.join(os.path.dirname(__file__), "PyQt6", "Qt6", "plugins")
os.environ["QT_PLUGIN_PATH"] = qt_plugin_path
"""
        return None