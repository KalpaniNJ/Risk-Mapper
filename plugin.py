import os
from qgis.core import QgsApplication
from .risk_provider import RiskMapperProvider

plugin_dir = os.path.dirname(__file__)

class RiskMapperPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.provider = None

    def initProcessing(self):
        self.provider = RiskMapperProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        self.initProcessing()

    def unload(self):
        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None