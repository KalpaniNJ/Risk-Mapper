from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterFile,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterString,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterRasterLayer,
    QgsProcessingException,
    QgsRasterLayer,
    QgsProject
)
from qgis import processing
import os

class ExposureAnalysisAlgorithm(QgsProcessingAlgorithm):
    BINARY_DIR = "BINARY_DIR"
    CROP_MASK = "CROP_MASK"
    OUTPUT_DIR = "OUTPUT_DIR"
    PREFIX = "PREFIX"
    LOAD_RESULT = "LOAD_RESULT"

    def tr(self, string):
        return QCoreApplication.translate("ExposureAnalysis", string)

    def createInstance(self):
        return ExposureAnalysisAlgorithm()

    def icon(self):
            plugin_dir = os.path.dirname(__file__)
            icon_path = os.path.join(plugin_dir, "icons", "exp_icon.jpeg")
            return QIcon(icon_path)

    def name(self):
        return "exposureanalysis"

    def displayName(self):
        return self.tr("Exposure maps")

    def group(self):
        return self.tr("2_Exposure analysis")

    def groupId(self):
        return "exposure_analysis"

    def shortHelpString(self):
        return self.tr("Masks exposure dataset (e.g. GDP, population) with binary frequency rasters to generate yearly exposure rasters.\n\n Note: The tool extracts the last 4 digits (year) from input raster filenames to ensure consistent file naming.")

    def initAlgorithm(self, config=None):
        # Binary rasters folder
        self.addParameter(
            QgsProcessingParameterFile(
                self.BINARY_DIR,
                self.tr("Binary raster folder"),
                behavior=QgsProcessingParameterFile.Folder
            )
        )

        # Exposure (mask) raster
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.CROP_MASK,
                self.tr("Exposure raster")
            )
        )

        # Output folder
        self.addParameter(
            QgsProcessingParameterFolderDestination(
                self.OUTPUT_DIR,
                self.tr("Output folder")
            )
        )

        # Prefix for output files
        self.addParameter(
            QgsProcessingParameterString(
                self.PREFIX,
                self.tr("Output file prefix"),
                defaultValue="_"
            )
        )

        # Load results checkbox
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.LOAD_RESULT,
                self.tr("Load layers on completion"),
                defaultValue=True
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        binary_dir = self.parameterAsFile(parameters, self.BINARY_DIR, context)
        crop_layer = self.parameterAsRasterLayer(parameters, self.CROP_MASK, context)
        crop_mask = crop_layer.source()
        output_dir = self.parameterAsFile(parameters, self.OUTPUT_DIR, context)
        prefix = self.parameterAsString(parameters, self.PREFIX, context)
        load_result = self.parameterAsBool(parameters, self.LOAD_RESULT, context)

        os.makedirs(output_dir, exist_ok=True)

        results = []

        # Loop through all rasters
        for filename in os.listdir(binary_dir):
            if not filename.lower().endswith(".tif"):
                continue

            binary_path = os.path.join(binary_dir, filename)

            # Extract year from filename (last 4 digits)
            year = ''.join(filter(str.isdigit, filename))[-4:]
            output_path = os.path.join(output_dir, f"{prefix}exposure_{year}.tif")

            feedback.pushInfo(f"Processing {filename} → {output_path}")

            binary_layer_name = os.path.splitext(filename)[0]
            crop_layer_name = os.path.splitext(os.path.basename(crop_mask))[0]

            calc_result = processing.run(
                "native:rastercalc",
                {
                    'LAYERS': [binary_path, crop_mask],
                    'EXPRESSION': f'"{binary_layer_name}@1" * "{crop_layer_name}@1"',
                    'OUTPUT': 'TEMPORARY_OUTPUT'
                },
                context=context,
                feedback=feedback
            )

            processing.run(
                "gdal:translate",
                {
                    'INPUT': calc_result['OUTPUT'],
                    'OPTIONS': 'COMPRESS=LZW',
                    'DATA_TYPE': None,
                    'OUTPUT': output_path
                },
                context=context,
                feedback=feedback
            )

            results.append(output_path)

            if load_result:
                rlayer = QgsRasterLayer(output_path, os.path.basename(output_path))
                if rlayer.isValid():
                    QgsProject.instance().addMapLayer(rlayer)

        feedback.pushInfo(f"Completed exposure analysis, saved {len(results)} rasters.")
        return {self.OUTPUT_DIR: output_dir}
