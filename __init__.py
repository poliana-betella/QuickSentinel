# -*- coding: utf-8 -*-
"""
QuickSentinel
Busca e download de imagens Sentinel-2 direto no QGIS.
"""


def classFactory(iface):
    from .quick_sentinel import QuickSentinelPlugin
    return QuickSentinelPlugin(iface)
