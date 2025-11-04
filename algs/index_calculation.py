from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterField,
    QgsProcessingParameterFile,
    QgsProcessingParameterVectorDestination,
)
import pandas as pd
import os
import processing


class CalculateIndexAlgorithm(QgsProcessingAlgorithm):
    INPUT_SHP = 'INPUT_SHP'
    JOIN_FIELD = 'JOIN_FIELD'
    INPUT_CSV = 'INPUT_CSV'
    WEIGHTS_CSV = 'WEIGHTS_CSV'
    OUTPUT_SHP = 'OUTPUT_SHP'

    def tr(self, string):
        return QCoreApplication.translate('IndexCalculation', string)

    def createInstance(self):
        return CalculateIndexAlgorithm()

    def icon(self):
            plugin_dir = os.path.dirname(__file__)
            icon_path = os.path.join(plugin_dir, "icons", "wi_icon.jpeg")
            return QIcon(icon_path)

    def name(self):
        return "IndexCalculation"

    def displayName(self):
        return self.tr("Calculate weighted index")

    def group(self):
        return self.tr("5_Statistical analysis")

    def groupId(self):
        return "statistical_analysis"

    def shortHelpString(self):
        return self.tr("Calculates a Weighted Index (wi, FWI) for hazard, exposure and vulnerability from CSV and joins results to a shapefile.")

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.INPUT_SHP,
                self.tr("Input vector layer"),
                [QgsProcessing.TypeVectorPolygon, QgsProcessing.TypeVectorPoint]
            )
        )

        self.addParameter(
            QgsProcessingParameterField(
                self.JOIN_FIELD,
                self.tr("Join field"),
                parentLayerParameterName=self.INPUT_SHP
            )
        )

        self.addParameter(
            QgsProcessingParameterFile(
                self.INPUT_CSV,
                self.tr("Input CSV with indicators"),
                extension="csv"
            )
        )

        self.addParameter(
            QgsProcessingParameterFile(
                self.WEIGHTS_CSV,
                self.tr("Weights CSV (indicator,weight)"),
                extension="csv"
            )
        )

        self.addParameter(
            QgsProcessingParameterVectorDestination(
                self.OUTPUT_SHP,
                self.tr("Output vector layer")
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        shp = self.parameterAsVectorLayer(parameters, self.INPUT_SHP, context)
        join_field = self.parameterAsString(parameters, self.JOIN_FIELD, context)
        input_csv = self.parameterAsFile(parameters, self.INPUT_CSV, context)
        weights_csv = self.parameterAsFile(parameters, self.WEIGHTS_CSV, context)
        output_shp = self.parameterAsOutputLayer(parameters, self.OUTPUT_SHP, context)

        df = pd.read_csv(input_csv)
        wdf = pd.read_csv(weights_csv)
        weights = dict(zip(wdf["indicator"], wdf["weight"]))
        indicators = list(weights.keys())
        feedback.pushInfo(f"Loaded {len(weights)} weights")

        # Standardize indicators
        for ind in indicators:
            if ind in df.columns:
                min_val, max_val = df[ind].min(skipna=True), df[ind].max(skipna=True)
                if max_val > min_val:
                    df[f"std_{ind}"] = (df[ind] - min_val) / (max_val - min_val)
                else:
                    df[f"std_{ind}"] = 0.0
            else:
                feedback.reportError(f"Indicator '{ind}' not found in CSV")

        # Apply weights
        for ind in indicators:
            std_col = f"std_{ind}"
            if std_col in df.columns:
                df[f"wei_{ind}"] = df[std_col] * weights[ind]

        # Compute Weighted Index (WI)
        weighted_cols = [f"wei_{ind}" for ind in indicators if f"wei_{ind}" in df.columns]
        df["WI"] = df[weighted_cols].mean(axis=1, skipna=True)

        # Compute FWI
        min_vi, max_vi = df["WI"].min(skipna=True), df["WI"].max(skipna=True)
        if max_vi > min_vi:
            df["FWI"] = (df["WI"] - min_vi) / (max_vi - min_vi)
        else:
            df["FWI"] = 0.0

        # Change data type of the join field
        df[join_field] = df[join_field].astype(str).str.strip()

        # Save CSV with WI and FWI
        output_csv = os.path.splitext(output_shp)[0] + "_FWI.csv"
        df.to_csv(output_csv, index=False)
        feedback.pushInfo(f"FWI CSV saved: {output_csv}")

        # Copy shapefile into a safe temporary layer (normalize join field)
        tmp_copy = processing.run(
            "native:refactorfields",
            {
                'INPUT': shp,
                'FIELDS_MAPPING': [
                    {'expression': f"trim(to_string(\"{join_field}\"))", 'name': join_field, 'type': 10, 'length': 255, 'precision': 0}
                ] + [
                    {'expression': f"\"{f.name()}\"", 'name': f.name(), 'type': f.type(), 'length': f.length(), 'precision': f.precision()}
                    for f in shp.fields() if f.name() != join_field
                ],
                'OUTPUT': 'memory:'
            },
            context=context,
            feedback=feedback
        )['OUTPUT']

        # Join CSV back to safe copy
        feedback.pushInfo("Joining FWI CSV back to shapefile...")
        join_result = processing.run(
            "native:joinattributestable",
            {
                'INPUT': tmp_copy,
                'FIELD': join_field,
                'INPUT_2': output_csv,
                'FIELD_2': join_field,
                'FIELDS_TO_COPY': ['WI', 'FWI'],
                'METHOD': 1,
                'DISCARD_NONMATCHING': False,
                'PREFIX': '',
                'OUTPUT': output_shp
            },
            context=context,
            feedback=feedback
        )

        feedback.pushInfo(f"Output shapefile saved: {output_shp}")
        return {self.OUTPUT_SHP: join_result['OUTPUT']}
