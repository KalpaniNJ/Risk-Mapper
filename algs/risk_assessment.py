from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterField,
    QgsProcessingParameterString,
    QgsProcessingParameterVectorDestination,
)
import processing
import os

class RiskAssessmentAlgorithm(QgsProcessingAlgorithm):
    BASE_LAYER = 'BASE_LAYER'
    JOIN_FIELD = 'JOIN_FIELD'
    HAZARD = 'HAZARD'
    HAZARD_FIELD = 'HAZARD_FIELD'
    VULNERABILITY = 'VULNERABILITY'
    VULNERABILITY_FIELD = 'VULNERABILITY_FIELD'
    EXPOSURE = 'EXPOSURE'
    EXPOSURE_FIELD = 'EXPOSURE_FIELD'
    ADAPTIVE = 'ADAPTIVE'
    ADAPTIVE_FIELD = 'ADAPTIVE_FIELD'
    EXPRESSION = 'EXPRESSION'
    OUTPUT = 'OUTPUT'

    def tr(self, string):
        return QCoreApplication.translate('RiskAssessment', string)

    def createInstance(self):
        return RiskAssessmentAlgorithm()
        
    def icon(self):
            plugin_dir = os.path.dirname(__file__)
            icon_path = os.path.join(plugin_dir, "icons", "risk_icon.jpeg")
            return QIcon(icon_path)

    def name(self):
        return "risk_assessment"

    def displayName(self):
        return self.tr("Calculate risk")

    def group(self):
        return self.tr("6_Risk assessment")

    def groupId(self):
        return "risk_assessment"

    def shortHelpString(self):
        return self.tr(
            "Combines hazard, vulnerability, exposure, and adaptive capacity using a user-defined formula and assess risk. "
            "User selects which fields to use from each layer. "
        )

    def initAlgorithm(self, config=None):
        # Base layer
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.BASE_LAYER,
                self.tr("Input vector layer"),
                [QgsProcessing.TypeVectorPolygon, QgsProcessing.TypeVectorPoint]
            )
        )

        # Join field
        self.addParameter(
            QgsProcessingParameterField(
                self.JOIN_FIELD,
                self.tr("Join field"),
                parentLayerParameterName=self.BASE_LAYER
            )
        )

        # Hazard
        self.addParameter(QgsProcessingParameterVectorLayer(self.HAZARD, "Hazard layer", optional=True))
        self.addParameter(
            QgsProcessingParameterField(
                self.HAZARD_FIELD,
                "Field from Hazard layer",
                parentLayerParameterName=self.HAZARD,
                optional=True
            )
        )

        # Vulnerability
        self.addParameter(QgsProcessingParameterVectorLayer(self.VULNERABILITY, "Vulnerability layer", optional=True))
        self.addParameter(
            QgsProcessingParameterField(
                self.VULNERABILITY_FIELD,
                "Field from Vulnerability layer",
                parentLayerParameterName=self.VULNERABILITY,
                optional=True
            )
        )

        # Exposure
        self.addParameter(QgsProcessingParameterVectorLayer(self.EXPOSURE, "Exposure layer", optional=True))
        self.addParameter(
            QgsProcessingParameterField(
                self.EXPOSURE_FIELD,
                "Field from Exposure layer",
                parentLayerParameterName=self.EXPOSURE,
                optional=True
            )
        )

        # Adaptive capacity
        self.addParameter(QgsProcessingParameterVectorLayer(self.ADAPTIVE, "Adaptive capacity layer", optional=True))
        self.addParameter(
            QgsProcessingParameterField(
                self.ADAPTIVE_FIELD,
                "Field from Adaptive capacity layer",
                parentLayerParameterName=self.ADAPTIVE,
                optional=True
            )
        )

        # Expression
        self.addParameter(
            QgsProcessingParameterString(
                self.EXPRESSION,
                self.tr("Formula (e.g., FHI * FEI * FVI / AC)")
            )
        )

        # Output
        self.addParameter(
            QgsProcessingParameterVectorDestination(
                self.OUTPUT,
                self.tr("Output layer")
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        base = self.parameterAsVectorLayer(parameters, self.BASE_LAYER, context)
        join_field = self.parameterAsString(parameters, self.JOIN_FIELD, context)
        expr = self.parameterAsString(parameters, self.EXPRESSION, context)
        output = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)

        # Input layers + fields
        hazard, hazard_field = self.parameterAsVectorLayer(parameters, self.HAZARD, context), self.parameterAsString(parameters, self.HAZARD_FIELD, context)
        vuln, vuln_field = self.parameterAsVectorLayer(parameters, self.VULNERABILITY, context), self.parameterAsString(parameters, self.VULNERABILITY_FIELD, context)
        expo, expo_field = self.parameterAsVectorLayer(parameters, self.EXPOSURE, context), self.parameterAsString(parameters, self.EXPOSURE_FIELD, context)
        adapt, adapt_field = self.parameterAsVectorLayer(parameters, self.ADAPTIVE, context), self.parameterAsString(parameters, self.ADAPTIVE_FIELD, context)

        # Function to filter out join field automatically
        def filter_field(layer, field_name):
            if not layer or not field_name:
                return None
            if field_name == join_field:
                feedback.pushInfo(f"Field '{field_name}' is the join key; skipping automatically.")
                return None
            return field_name

        hazard_field = filter_field(hazard, hazard_field)
        vuln_field = filter_field(vuln, vuln_field)
        expo_field = filter_field(expo, expo_field)
        adapt_field = filter_field(adapt, adapt_field)

        # Layers to join: (layer, field, prefix)
        layers_to_join = [
            (hazard, hazard_field, "FHI"),
            (vuln, vuln_field, "FVI"),
            (expo, expo_field, "FEI"),
            (adapt, adapt_field, "AC")
        ]

        working = base

        for lyr, field_name, alias in layers_to_join:
            if lyr is None or not field_name:
                feedback.pushInfo(f"Skipping {alias} (not provided or join key).")
                continue
            feedback.pushInfo(f"Joining {alias} field: {field_name}")
            join_result = processing.run(
                "native:joinattributestable",
                {
                    'INPUT': working,
                    'FIELD': join_field,
                    'INPUT_2': lyr,
                    'FIELD_2': join_field,
                    'FIELDS_TO_COPY': [field_name],  # only selected field
                    'METHOD': 1,
                    'DISCARD_NONMATCHING': False,
                    'PREFIX': "",
                    'OUTPUT': 'TEMPORARY_OUTPUT'
                },
                context=context,
                feedback=feedback
            )
            working = join_result['OUTPUT']

        # Evaluate expression
        feedback.pushInfo(f"Calculating Risk using expression: {expr}")
        calc_result = processing.run(
            "native:fieldcalculator",
            {
                'INPUT': working,
                'FIELD_NAME': 'RISK',
                'FIELD_TYPE': 0,  # Float
                'FIELD_LENGTH': 20,
                'FIELD_PRECISION': 6,
                'FORMULA': expr,
                'OUTPUT': output
            },
            context=context,
            feedback=feedback
        )

        return {self.OUTPUT: calc_result['OUTPUT']}
