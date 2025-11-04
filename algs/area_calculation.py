from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterFile,
    QgsProcessingParameterString,
    QgsProcessingParameterEnum,
    QgsProcessingParameterNumber,
    QgsProcessingParameterVectorDestination,
    QgsVectorLayer,
    QgsRasterLayer,
    QgsProject
)
import os
import glob
import processing


class ZonalStatsWithAreaCalculationAlgorithm(QgsProcessingAlgorithm):
    ADMIN_LAYER = "ADMIN_LAYER"
    RASTER_FOLDER = "RASTER_FOLDER"
    PREFIX = "PREFIX"
    PIXEL_AREA = "PIXEL_AREA"
    STATISTIC = "STATISTIC"
    OUTPUT_VECTOR = "OUTPUT_VECTOR"

    def tr(self, string):
        return QCoreApplication.translate("ZonalStatsWithAreaCalcAlgorithm", string)

    def createInstance(self):
        return ZonalStatsWithAreaCalculationAlgorithm()
        
    def icon(self):
            plugin_dir = os.path.dirname(__file__)
            icon_path = os.path.join(plugin_dir, "icons", "area_icon.jpeg")
            return QIcon(icon_path)

    def name(self):
        return "area_calculation"

    def displayName(self):
        return self.tr("Calculate area")

    def group(self):
        return self.tr("5_Statistical analysis")

    def groupId(self):
        return "statistical_analysis"

    def shortHelpString(self):
        return self.tr(
            "Calculates zonal statistics for multiple rasters, derives areas based on pixel counts or sums. \n\n Note: The text following the last underscore in each raster filename is extracted to ensure consistent field naming."
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
                defaultValue="_"
            )
        )

        # Which statistic to use for area calculation
        self.addParameter(
            QgsProcessingParameterEnum(
                self.STATISTIC,
                self.tr("Statistic for area calculation"),
                options=["Count", "Sum"],
                defaultValue=0
            )
        )

        # User-defined pixel area (optional)
        self.addParameter(
            QgsProcessingParameterNumber(
                self.PIXEL_AREA,
                self.tr("Pixel area (m²)"),
                type=QgsProcessingParameterNumber.Double,
                defaultValue=None,
                optional=True
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
        user_pixel_area = self.parameterAsDouble(parameters, self.PIXEL_AREA, context)
        stat_idx = self.parameterAsEnum(parameters, self.STATISTIC, context)
        output_vector = self.parameterAsOutputLayer(parameters, self.OUTPUT_VECTOR, context)

        # map to zonalstatisticsfb codes
        stat_map = {0: 0, 1: 1}  # Count=0, Sum=1
        stat_code = stat_map[stat_idx]

        raster_files = sorted(glob.glob(os.path.join(raster_folder, "*.tif")))
        feedback.pushInfo(f"Found {len(raster_files)} raster(s)")

        result_layer = admin_layer

        for i, raster_path in enumerate(raster_files, start=1):
            raster_name = os.path.splitext(os.path.basename(raster_path))[0]
            suffix = raster_name.split("_")[-1]

            feedback.pushInfo(f"[{i}/{len(raster_files)}] Processing {raster_name}")

            # run zonal statistics
            result = processing.run(
                "native:zonalstatisticsfb",
                {
                    "INPUT": result_layer,
                    "INPUT_RASTER": raster_path,
                    "RASTER_BAND": 1,
                    "COLUMN_PREFIX": f"{suffix}_",
                    "STATISTICS": [stat_code],
                    "OUTPUT": "memory:",
                },
                context=context,
                feedback=feedback,
            )
            zonal_layer = result["OUTPUT"]

            # Decide pixel area: use user input or derive from raster resolution
            if user_pixel_area:
                pixel_area = user_pixel_area
            else:
                rlayer = QgsRasterLayer(raster_path, "raster_tmp")
                if not rlayer.isValid():
                    raise QgsProcessingException(f"Invalid raster: {raster_path}")
                pixel_area = abs(rlayer.rasterUnitsPerPixelX() * rlayer.rasterUnitsPerPixelY())

            if stat_idx == 0:
                stat_field = f"{suffix}_count"
            else:
                stat_field = f"{suffix}_sum"

            area_field = f"{prefix}{suffix}_km2"

            zonal_with_area = processing.run(
                "qgis:fieldcalculator",
                {
                    "INPUT": zonal_layer,
                    "FIELD_NAME": area_field,
                    "FIELD_TYPE": 0,  # Double
                    "FIELD_LENGTH": 20,
                    "FIELD_PRECISION": 4,
                    "FORMULA": f'"{stat_field}" * {pixel_area} / 1000000',
                    "OUTPUT": "memory:",
                },
                context=context,
                feedback=feedback,
            )["OUTPUT"]

            # update working layer for next join
            result_layer = zonal_with_area

        # Save final result
        processing.run(
            "native:savefeatures",
            {"INPUT": result_layer, "OUTPUT": output_vector},
            context=context,
            feedback=feedback,
        )

        final_layer = QgsVectorLayer(output_vector, "Zonal Stats Area", "ogr")
        if final_layer.isValid():
            QgsProject.instance().addMapLayer(final_layer)

        return {self.OUTPUT_VECTOR: output_vector}
