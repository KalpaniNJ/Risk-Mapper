import os
import inspect
from PyQt5.QtGui import QIcon

from qgis.core import QgsProcessingProvider
from .algs.binary_conversion import BinaryConversionAlgorithm
from .algs.merge_mask_reproject import MergeMaskReprojectAlgorithm
from .algs.yearly_frequency import YearlyFrequencyAlgorithm
from .algs.monthly_frequency import MonthlyFrequencyAlgorithm
from .algs.seasonal_frequency import SeasonalFrequencyAlgorithm
from .algs.frequency_summation import SummationAlgorithm
from .algs.exposure_analysis import ExposureAnalysisAlgorithm
from .algs.vulnerability_analysis import VulnerabilityAnalysisAlgorithm
from .algs.exposure_vulnerability_analysis import ExposureVulnerabilityAnalysisAlgorithm
from .algs.zonal_statistics_multiple_rasters import ZonalStatsMultipleRastersAlgorithm
from .algs.area_calculation import ZonalStatsWithAreaCalculationAlgorithm
from .algs.monthly_zonal_statistics import MonthlyZonalStatsAlgorithm
from .algs.vulnerability_zonal_statistics import VulnerabilityStatsAlgorithm
from .algs.exposure_sampling_count import PointSamplingCountAlgorithm
from .algs.index_calculation import CalculateIndexAlgorithm
from .algs.risk_assessment import RiskAssessmentAlgorithm

plugin_dir = os.path.dirname(__file__)

class RiskMapperProvider(QgsProcessingProvider):
    PROVIDER_ID = 'risk'
    def id(self):
        return self.PROVIDER_ID

    def __init__(self):
        QgsProcessingProvider.__init__(self)

    def unload(self):
        QgsProcessingProvider.unload(self)

    def loadAlgorithms(self):
	# Add algorithms here.
        self.addAlgorithm(BinaryConversionAlgorithm())
        self.addAlgorithm(MergeMaskReprojectAlgorithm())
        self.addAlgorithm(YearlyFrequencyAlgorithm())
        self.addAlgorithm(MonthlyFrequencyAlgorithm())
        self.addAlgorithm(SeasonalFrequencyAlgorithm())
        self.addAlgorithm(SummationAlgorithm())
        self.addAlgorithm(ExposureAnalysisAlgorithm())
        self.addAlgorithm(VulnerabilityAnalysisAlgorithm())
        self.addAlgorithm(ExposureVulnerabilityAnalysisAlgorithm())
        self.addAlgorithm(ZonalStatsMultipleRastersAlgorithm())
        self.addAlgorithm(ZonalStatsWithAreaCalculationAlgorithm())
        self.addAlgorithm(MonthlyZonalStatsAlgorithm())
        self.addAlgorithm(VulnerabilityStatsAlgorithm())
        self.addAlgorithm(PointSamplingCountAlgorithm())
        self.addAlgorithm(CalculateIndexAlgorithm())
        self.addAlgorithm(RiskAssessmentAlgorithm())

    def name(self):
        return self.tr('Risk Mapper')

    def icon(self):
        icon = QIcon(os.path.join(os.path.join(plugin_dir, 'icon.jpg')))
        return icon

    def longName(self):
        return self.name()