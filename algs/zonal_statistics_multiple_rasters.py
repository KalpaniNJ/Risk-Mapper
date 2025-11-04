from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterFile,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterString,
    QgsProcessingParameterEnum,
    QgsProcessingParameterVectorDestination,
    QgsVectorLayer,
    QgsProject
)
import os
import glob
import processing

class ZonalStatsMultipleRastersAlgorithm(QgsProcessingAlgorithm):
    ADMIN_LAYER = "ADMIN_LAYER"
    RASTER_FOLDER = "RASTER_FOLDER"
    PREFIX = "PREFIX"
    STATISTIC = "STATISTIC"
    OUTPUT_VECTOR = "OUTPUT_VECTOR"

    def tr(self, string):
        return QCoreApplication.translate("ZonalStatsMultipleRastersAlgorithm", string)

    def createInstance(self):
        return ZonalStatsMultipleRastersAlgorithm()

    def icon(self):
            plugin_dir = os.path.dirname(__file__)
            icon_path = os.path.join(plugin_dir, "icons", "zonal_icon.jpeg")
            return QIcon(icon_path)

    def name(self):
        return "zonal_statistics_multiple_rasters"

    def displayName(self):
        return self.tr("Calculate zonal statistics")

    def group(self):
        return self.tr("5_Statistical analysis")

    def groupId(self):
        return "statistical_analysis"

    def shortHelpString(self):
        return self.tr(
            "Calculates zonal statistics for all rasters in a folder and appends the results to the input vector layer. \n\n Note: The text following the last underscore in each raster filename is extracted to ensure consistent field naming."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.ADMIN_LAYER,
                self.tr("Input vector layer"),
                [QgsProcessing.TypeVectorPolygon]
            )
        )

        self.addParameter(
            QgsProcessingParameterFile(
                self.RASTER_FOLDER,
                self.tr("Input folder with rasters"),
                behavior=QgsProcessingParameterFile.Folder
            )
        )

        self.addParameter(
            QgsProcessingParameterString(
                self.PREFIX,
                self.tr("Output column prefix"),
                defaultValue="stat_"
            )
        )

        self.addParameter(
            QgsProcessingParameterEnum(
                self.STATISTIC,
                self.tr("Statistic to calculate"),
                options=["Sum", "Mean", "Min", "Max", "Count"],
                defaultValue=0
            )
        )

        self.addParameter(
            QgsProcessingParameterVectorDestination(
                self.OUTPUT_VECTOR,
                self.tr("Output vector layer")
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        admin_layer = self.parameterAsVectorLayer(parameters, self.ADMIN_LAYER, context)
        raster_folder = self.parameterAsString(parameters, self.RASTER_FOLDER, context)
        prefix = self.parameterAsString(parameters, self.PREFIX, context)
        stat_idx = self.parameterAsEnum(parameters, self.STATISTIC, context)
        output_vector = self.parameterAsOutputLayer(parameters, self.OUTPUT_VECTOR, context)

        # map enum to zonalstatisticsfb codes
        stat_map = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5}
        stat_code = stat_map[stat_idx]

        raster_files = glob.glob(os.path.join(raster_folder, "*.tif"))
        feedback.pushInfo(f"Found {len(raster_files)} raster(s)")

        result_layer = admin_layer

        for i, raster_path in enumerate(raster_files, start=1):
            raster_name = os.path.splitext(os.path.basename(raster_path))[0]
            suffix = raster_name.split("_")[-1]
            field_prefix = f"{prefix}{suffix}_"

            feedback.pushInfo(f"[{i}/{len(raster_files)}] Processing {raster_name}")

            result = processing.run("native:zonalstatisticsfb", {
                'INPUT': result_layer,
                'INPUT_RASTER': raster_path,
                'RASTER_BAND': 1,
                'COLUMN_PREFIX': field_prefix,
                'STATISTICS': [stat_code],
                'OUTPUT': 'memory:'
            }, context=context, feedback=feedback)

            result_layer = result['OUTPUT']

        # Save final result directly to chosen output
        processing.run("native:savefeatures", {
            'INPUT': result_layer,
            'OUTPUT': output_vector
        }, context=context, feedback=feedback)

        final_layer = QgsVectorLayer(output_vector, "Zonal Stats Final", "ogr")
        if final_layer.isValid():
            QgsProject.instance().addMapLayer(final_layer)

        return {self.OUTPUT_VECTOR: output_vector}
