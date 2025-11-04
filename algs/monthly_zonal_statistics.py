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
    QgsProject,
    QgsProcessingException
)
import os
import glob
import processing


class MonthlyZonalStatsAlgorithm(QgsProcessingAlgorithm):
    ADMIN_LAYER = "ADMIN_LAYER"
    RASTER_FOLDER = "RASTER_FOLDER"
    PREFIX = "PREFIX"
    DATE_ID = "DATE_ID"
    PIXEL_AREA = "PIXEL_AREA"
    STATISTIC = "STATISTIC"
    OUTPUT_VECTOR = "OUTPUT_VECTOR"

    def tr(self, string):
        return QCoreApplication.translate("MonthlyZonalStatsAlgorithm", string)

    def createInstance(self):
        return MonthlyZonalStatsAlgorithm()
        
    def icon(self):
            plugin_dir = os.path.dirname(__file__)
            icon_path = os.path.join(plugin_dir, "icons", "month_icon.jpeg")
            return QIcon(icon_path)

    def name(self):
        return "monthly_zonal_statistics"

    def displayName(self):
        return self.tr("Calculate monthly zonal area")

    def group(self):
        return self.tr("5_Statistical analysis")

    def groupId(self):
        return "statistical_analysis"

    def shortHelpString(self):
        return self.tr(
            "Calculates monthly zonal statistics for multiple rasters, "
            "and derives area (km²) using either Count or Sum statistics. "
            "Suffix for output fields can be extracted using user-defined slicing (e.g., '2:7')."
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
                defaultValue="fd_"
            )
        )

        self.addParameter(
            QgsProcessingParameterString(
                self.DATE_ID,
                self.tr("Date identifier (e.g. 2:7, -8:-4)"),
                defaultValue="2:7"
            )
        )

        self.addParameter(
            QgsProcessingParameterEnum(
                self.STATISTIC,
                self.tr("Statistic for area calculation"),
                options=["Count", "Sum"],
                defaultValue=1
            )
        )

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
        date_id = self.parameterAsString(parameters, self.DATE_ID, context)
        user_pixel_area = self.parameterAsDouble(parameters, self.PIXEL_AREA, context)
        stat_idx = self.parameterAsEnum(parameters, self.STATISTIC, context)
        output_vector = self.parameterAsOutputLayer(parameters, self.OUTPUT_VECTOR, context)

        stat_map = {0: 0, 1: 1}
        stat_code = stat_map[stat_idx]

        raster_files = sorted(glob.glob(os.path.join(raster_folder, "*.tif")))
        feedback.pushInfo(f"Found {len(raster_files)} raster(s)")

        result_layer = admin_layer

        # Parse slicing string "2:7" -> date part(2,7)
        try:
            start, end = date_id.split(":")
            start = int(start) if start else None
            end = int(end) if end else None
            slice_obj = slice(start, end)
        except Exception:
            raise QgsProcessingException(
                f"Invalid date identifier '{date_id}'."
            )

        for i, raster_path in enumerate(raster_files, start=1):
            raster_name = os.path.splitext(os.path.basename(raster_path))[0]

            date_part = raster_name.split("_")[-2]
            suffix = date_part[slice_obj]

            feedback.pushInfo(f"[{i}/{len(raster_files)}] Processing {raster_name} -> date part {suffix}")

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

            if user_pixel_area:
                pixel_area = user_pixel_area
            else:
                rlayer = QgsRasterLayer(raster_path, "raster_tmp")
                if not rlayer.isValid():
                    raise QgsProcessingException(f"Invalid raster: {raster_path}")
                pixel_area = abs(rlayer.rasterUnitsPerPixelX() * rlayer.rasterUnitsPerPixelY())

            stat_field = f"{suffix}_{'count' if stat_idx == 0 else 'sum'}"
            area_field = f"{prefix}{suffix}_km2"

            zonal_with_area = processing.run(
                "qgis:fieldcalculator",
                {
                    "INPUT": zonal_layer,
                    "FIELD_NAME": area_field,
                    "FIELD_TYPE": 0,
                    "FIELD_LENGTH": 20,
                    "FIELD_PRECISION": 4,
                    "FORMULA": f'"{stat_field}" * {pixel_area} / 1000000',
                    "OUTPUT": "memory:",
                },
                context=context,
                feedback=feedback,
            )["OUTPUT"]

            result_layer = zonal_with_area

        processing.run(
            "native:savefeatures",
            {"INPUT": result_layer, "OUTPUT": output_vector},
            context=context,
            feedback=feedback,
        )

        final_layer = QgsVectorLayer(output_vector, "Monthly Zonal Stats", "ogr")
        if final_layer.isValid():
            QgsProject.instance().addMapLayer(final_layer)

        return {self.OUTPUT_VECTOR: output_vector}
