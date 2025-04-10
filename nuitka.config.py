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

# 打包配置
def nuitka_module_config(module_name):
    if module_name == "__main__":
        return {
            "enable_plugin_multiprocessing": True,
            "enable_plugin_numpy": False,
            "enable_plugin_qt": True,
            "enable_plugin_tk": False,
            "enable_plugin_torch": False,
            "enable_plugin_tensorflow": False,
            "enable_plugin_matplotlib": False,
            "enable_plugin_scipy": False,
            "enable_plugin_pandas": False,
            "enable_plugin_pillow": True,
            "enable_plugin_requests": True,
            "enable_plugin_qrcode": True,
            "enable_plugin_pyside6": False,
            "enable_plugin_pyqt5": False,
            "enable_plugin_pyqt6": True,
            "windows_icon_from_ico": None,
            "windows_company_name": "WatererQuan",
            "windows_product_name": "BiliDown-GUI",
            "windows_file_version": "1.0.0.0",
            "windows_product_version": "1.0.0.0",
            "windows_file_description": "BiliDown-GUI",
            "windows_disable_console": True,
            "onefile": True,
            "assume_yes_for_downloads": True,
            "include_qt_plugins": [
                "platforms",
                "styles",
                "imageformats"
            ]
        }
    return None