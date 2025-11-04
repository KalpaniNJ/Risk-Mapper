from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterFile,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterString,
    QgsProcessingParameterVectorDestination,
    QgsVectorLayer,
    QgsProject
)

import os
import re
import processing

class PointSamplingCountAlgorithm(QgsProcessingAlgorithm):
    ADMIN = "ADMIN"
    CENTROIDS = "CENTROIDS"
    RASTER_FOLDER = "RASTER_FOLDER"
    PREFIX = "PREFIX"
    OUTPUT = "OUTPUT"

    def tr(self, text):
        return QCoreApplication.translate("PointSamplingCountAlgorithm", text)

    def createInstance(self):
        return PointSamplingCountAlgorithm()
        
    def icon(self):
            plugin_dir = os.path.dirname(__file__)
            icon_path = os.path.join(plugin_dir, "icons", "pts_icon.jpeg")
            return QIcon(icon_path)

    def name(self):
        return "exposure_sampling_count"

    def displayName(self):
        return self.tr("Count points")

    def group(self):
        return self.tr("5_Statistical analysis")

    def groupId(self):
        return "statistical_analysis"

    def shortHelpString(self):
        return self.tr(
            "Samples multiple rasters at centroids, aggregates all sampled fields into one layer, and summarizes counts per admin unit in one step. \n\n Note: The text following the last underscore in each raster filename is extracted to ensure consistent field naming."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.ADMIN,
                self.tr("Admin boundaries"),
                [QgsProcessing.TypeVectorPolygon]
            )
        )

        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.CENTROIDS,
                self.tr("Centroid points layer"),
                [QgsProcessing.TypeVectorPoint]
            )
        )

        self.addParameter(
            QgsProcessingParameterFile(
                self.RASTER_FOLDER,
                self.tr("Folder containing raster files"),
                behavior=QgsProcessingParameterFile.Folder
            )
        )

        self.addParameter(
            QgsProcessingParameterString(
                self.PREFIX,
                self.tr("Output column prefix"),
                defaultValue="pts_"
            )
        )

        self.addParameter(
            QgsProcessingParameterVectorDestination(
                self.OUTPUT,
                self.tr("Final output")
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        admin_layer = self.parameterAsVectorLayer(parameters, self.ADMIN, context)
        centroids_layer = self.parameterAsVectorLayer(parameters, self.CENTROIDS, context)
        raster_folder = self.parameterAsString(parameters, self.RASTER_FOLDER, context)
        prefix = self.parameterAsString(parameters, self.PREFIX, context)
        output_vector = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)

        # Collect raster files
        raster_files = sorted([os.path.join(raster_folder, f) for f in os.listdir(raster_folder) if f.endswith(".tif")])
        feedback.pushInfo(f"Found {len(raster_files)} raster(s)")

        # Initialize cumulative memory layer with centroids
        cumulative_layer = QgsVectorLayer(f'Point?crs={centroids_layer.crs().authid()}', 'cumulative', 'memory')
        cumulative_provider = cumulative_layer.dataProvider()
        cumulative_provider.addAttributes(centroids_layer.fields())
        cumulative_layer.updateFields()
        cumulative_provider.addFeatures(centroids_layer.getFeatures())

        # Loop through rasters and add sampled fields
        for i, raster_path in enumerate(raster_files, start=1):
            raster_name = os.path.splitext(os.path.basename(raster_path))[0]
            suffix_match = re.search(r'(\d{4})', raster_name)
            suffix = suffix_match.group(1) if suffix_match else raster_name.split("_")[-1]
            field_prefix = f"{prefix}{suffix}_"

            feedback.pushInfo(f"[{i}/{len(raster_files)}] Sampling {raster_name}")

            sampled = processing.run("native:rastersampling", {
                'INPUT': cumulative_layer,
                'RASTERCOPY': raster_path,
                'COLUMN_PREFIX': field_prefix,
                'OUTPUT': 'memory:'
            }, context=context, feedback=feedback)['OUTPUT']

            # Update cumulative layer
            cumulative_layer = sampled

        # Select only points with any positive value for counts
        fields_to_count = [f.name() for f in cumulative_layer.fields() if f.name() not in [f.name() for f in centroids_layer.fields()]]
        # (You can filter per field if needed during join)

        # Perform one final spatial summary join with admin layer
        join_result = processing.run("native:joinbylocationsummary", {
            'INPUT': admin_layer,
            'PREDICATE': [0, 1, 4, 5],  # intersects, contains, within, touches
            'JOIN': cumulative_layer,
            'JOIN_FIELDS': fields_to_count,
            'SUMMARIES': [0],  # count
            'DISCARD_NONMATCHING': False,
            'OUTPUT': output_vector
        }, context=context, feedback=feedback)['OUTPUT']

        final_layer = QgsVectorLayer(join_result, "Exposure Zonal Stats", "ogr")
        
        if final_layer.isValid():
            QgsProject.instance().addMapLayer(final_layer)
            feedback.pushInfo(f"Final layer created with all counts at {output_vector}")

        return {self.OUTPUT: output_vector}
