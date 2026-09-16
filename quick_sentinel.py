# -*- coding: utf-8 -*-
import os

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction


class QuickSentinelPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dialog = None

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        icon = QIcon(icon_path) if os.path.isfile(icon_path) else QIcon()

        self.action = QAction(icon, "QuickSentinel — Buscar imagens Sentinel-2...", self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addPluginToMenu("&QuickSentinel", self.action)
        self.iface.addRasterToolBarIcon(self.action)

    def unload(self):
        if self.action:
            self.iface.removePluginMenu("&QuickSentinel", self.action)
            self.iface.removeRasterToolBarIcon(self.action)

    def run(self):
        from .quick_sentinel_dialog import QuickSentinelDialog
        self.dialog = QuickSentinelDialog(self.iface, parent=self.iface.mainWindow())
        self.dialog.show()
