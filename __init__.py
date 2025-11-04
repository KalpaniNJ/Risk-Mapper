from .plugin import RiskMapperPlugin

def classFactory(iface):
	return RiskMapperPlugin(iface)