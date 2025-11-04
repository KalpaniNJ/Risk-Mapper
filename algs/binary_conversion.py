from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterRasterDestination,
    QgsProcessingParameterNumber,
    QgsProcessingParameterEnum
)
from osgeo import gdal
import numpy as np
import os

class BinaryConversionAlgorithm(QgsProcessingAlgorithm):
    INPUT = 'INPUT'
    THRESHOLD = 'THRESHOLD'
    COMPRESSION = 'COMPRESSION'
    OUTPUT = 'OUTPUT'

    COMPRESSION_TYPES = [
        'None',
        'LZW',
        'DEFLATE',
        'PACKBITS'
    ]

    def name(self):
        return 'binary_conversion'

    def displayName(self):
        return self.tr('Raster binary converter')

    def group(self):
        return self.tr('0_Raster preprocessing')

    def groupId(self):
        return 'raster_preprocessing'

    def shortHelpString(self):
        return self.tr(
            'Converts an input raster to a binary raster (0/1) based on a threshold. '
            'Values greater than the threshold are set to 1, otherwise 0. Compression can be chosen.'
        )

    def tr(self, string):
        return QCoreApplication.translate('BinaryConversionAlgorithm', string)

    def createInstance(self):
        return BinaryConversionAlgorithm()
        
    def icon(self):
            plugin_dir = os.path.dirname(__file__)
            icon_path = os.path.join(plugin_dir, "icons", "binary_icon.jpeg")
            return QIcon(icon_path)

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterRasterLayer(self.INPUT, self.tr('Input raster'))
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.THRESHOLD,
                self.tr('Threshold'),
                type=QgsProcessingParameterNumber.Double,
                defaultValue=0
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.COMPRESSION,
                self.tr('Compression'),
                options=self.COMPRESSION_TYPES,
                defaultValue=0
            )
        )
        self.addParameter(
            QgsProcessingParameterRasterDestination(self.OUTPUT, self.tr('Output binary raster'))
        )

    def processAlgorithm(self, parameters, context, feedback):
        in_raster = self.parameterAsRasterLayer(parameters, self.INPUT, context)
        threshold = self.parameterAsDouble(parameters, self.THRESHOLD, context)
        comp_index = self.parameterAsInt(parameters, self.COMPRESSION, context)
        out_raster = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)

        # Open input raster
        ds = gdal.Open(in_raster.source())
        band = ds.GetRasterBand(1)
        arr = band.ReadAsArray()
        nodata = band.GetNoDataValue()
        if nodata is not None:
            arr[arr == nodata] = 0

        # Apply binary threshold
        binary = np.where(arr > threshold, 1, 0).astype(np.uint8)

        # Prepare GDAL options
        gdal_options = []
        if comp_index > 0:
            gdal_options.append(f"COMPRESS={self.COMPRESSION_TYPES[comp_index]}")

        # Always use Byte for binary raster
        gdal_dtype = gdal.GDT_Byte

        # Create output raster
        driver = gdal.GetDriverByName('GTiff')
        out_ds = driver.Create(
            out_raster,
            ds.RasterXSize,
            ds.RasterYSize,
            1,
            gdal_dtype,
            options=gdal_options
        )
        out_ds.SetGeoTransform(ds.GetGeoTransform())
        out_ds.SetProjection(ds.GetProjection())
        out_band = out_ds.GetRasterBand(1)
        out_band.WriteArray(binary)
        out_band.SetNoDataValue(0)
        out_ds.FlushCache()
        out_ds = None
        ds = None

        return {self.OUTPUT: out_raster}
