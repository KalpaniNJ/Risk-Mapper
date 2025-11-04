from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterFile,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterEnum,
    QgsProcessingParameterBoolean,
    QgsRasterLayer,
    QgsProject
)
import os
import numpy as np
from osgeo import gdal

class SummationAlgorithm(QgsProcessingAlgorithm):
    INPUT_FOLDER = "INPUT_FOLDER"
    OUTPUT_RASTER = "OUTPUT_RASTER"
    OUT_DATATYPE = "OUT_DATATYPE"
    COMPRESSION = "COMPRESSION"
    LOAD_RESULT = "LOAD_RESULT"

    def tr(self, string):
        return QCoreApplication.translate("SummationAlgorithm", string)

    def createInstance(self):
        return SummationAlgorithm()
        
    def icon(self):
            plugin_dir = os.path.dirname(__file__)
            icon_path = os.path.join(plugin_dir, "icons", "all_icon.jpeg")
            return QIcon(icon_path)  

    def name(self):
        return "frequencysummation"

    def displayName(self):
        return self.tr("Hazard map")

    def group(self):
        return self.tr("1_Hazard analysis")

    def groupId(self):
        return "hazard_analysis"

    def shortHelpString(self):
        return self.tr(
            "Recursively sums all rasters in a folder to create a hazard map. "
        )

    def initAlgorithm(self, config=None):
        # Input folder
        self.addParameter(
            QgsProcessingParameterFile(
                self.INPUT_FOLDER,
                self.tr("Input main folder"),
                behavior=QgsProcessingParameterFile.Folder
            )
        )

        # Output raster
        self.addParameter(
            QgsProcessingParameterFileDestination(
                self.OUTPUT_RASTER,
                self.tr("Output raster"),
                fileFilter="GeoTIFF (*.tif)"
            )
        )

        # Data type dropdown
        self.addParameter(
            QgsProcessingParameterEnum(
                self.OUT_DATATYPE,
                self.tr("Output data type"),
                options=[
                    "Byte",
                    "UInt16",
                    "UInt32",
                    "Int16",
                    "Int32",
                    "Float32",
                    "Float64"
                ],
                defaultValue=5  # Float32
            )
        )

        # Compression dropdown
        self.addParameter(
            QgsProcessingParameterEnum(
                self.COMPRESSION,
                self.tr("Compression"),
                options=["None", "LZW", "DEFLATE", "PACKBITS"],
                defaultValue=0  # None
            )
        )

        # Load result checkbox
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.LOAD_RESULT,
                self.tr("Load layers on completion"),
                defaultValue=True
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        input_folder = self.parameterAsFile(parameters, self.INPUT_FOLDER, context)
        output_raster = self.parameterAsFile(parameters, self.OUTPUT_RASTER, context)
        dtype_idx = self.parameterAsEnum(parameters, self.OUT_DATATYPE, context)
        compression_idx = self.parameterAsEnum(parameters, self.COMPRESSION, context)
        load_result = self.parameterAsBool(parameters, self.LOAD_RESULT, context)

        # Map enum to GDAL types
        gdal_dtype_map = {
            0: gdal.GDT_Byte,
            1: gdal.GDT_UInt16,
            2: gdal.GDT_UInt32,
            3: gdal.GDT_Int16,
            4: gdal.GDT_Int32,
            5: gdal.GDT_Float32,
            6: gdal.GDT_Float64
        }
        out_gdal_dtype = gdal_dtype_map.get(dtype_idx, gdal.GDT_UInt16)

        # Map compression
        compression_map = {0: None, 1: "LZW", 2: "DEFLATE", 3: "PACKBITS"}
        compression_val = compression_map.get(compression_idx)

        # Gather all TIFFs recursively
        all_rasters = []
        for root, _, files in os.walk(input_folder):
            for fname in files:
                if fname.lower().endswith(".tif"):
                    all_rasters.append(os.path.join(root, fname))

        if not all_rasters:
            raise QgsProcessingException("No TIFF files found under the input folder.")

        feedback.pushInfo(f"Found {len(all_rasters)} TIFF(s) to include in summation.")

        # Read metadata from first raster
        sample_ds = gdal.Open(all_rasters[0])
        geo = sample_ds.GetGeoTransform()
        proj = sample_ds.GetProjection()
        cols = sample_ds.RasterXSize
        rows = sample_ds.RasterYSize
        sample_ds = None

        # Create GDAL options
        creation_options = []
        if compression_val:
            creation_options.append(f"COMPRESS={compression_val}")

        driver = gdal.GetDriverByName("GTiff")
        out_ds = driver.Create(output_raster, cols, rows, 1, out_gdal_dtype, options=creation_options)
        out_ds.SetGeoTransform(geo)
        out_ds.SetProjection(proj)
        out_band = out_ds.GetRasterBand(1)
        out_band.SetNoDataValue(0)

        # Process rasters in blocks
        block_size = 512
        for y in range(0, rows, block_size):
            ysize = min(block_size, rows - y)
            for x in range(0, cols, block_size):
                xsize = min(block_size, cols - x)
                block_sum = np.zeros((ysize, xsize), dtype=np.uint32)  # safe accumulator

                for raster_path in all_rasters:
                    ds = gdal.Open(raster_path)
                    band = ds.GetRasterBand(1)
                    data = band.ReadAsArray(x, y, xsize, ysize).astype(np.uint32)
                    nodata = band.GetNoDataValue()
                    ds = None

                    if nodata is not None:
                        data[data == nodata] = 0

                    block_sum += data

                # Cast to output type safely
                if out_gdal_dtype == gdal.GDT_Byte:
                    out_block = np.clip(block_sum, 0, 255).astype(np.uint8)
                elif out_gdal_dtype == gdal.GDT_UInt16:
                    out_block = np.clip(block_sum, 0, 65535).astype(np.uint16)
                elif out_gdal_dtype == gdal.GDT_UInt32:
                    out_block = np.clip(block_sum, 0, 4294967295).astype(np.uint32)
                elif out_gdal_dtype == gdal.GDT_Int16:
                    out_block = np.clip(block_sum, -32768, 32767).astype(np.int16)
                elif out_gdal_dtype == gdal.GDT_Int32:
                    out_block = np.clip(block_sum, -2147483648, 2147483647).astype(np.int32)
                elif out_gdal_dtype == gdal.GDT_Float32:
                    out_block = block_sum.astype(np.float32)
                else:
                    out_block = block_sum.astype(np.float64)

                out_band.WriteArray(out_block, xoff=x, yoff=y)

            feedback.setProgress(int(100.0 * (y + ysize) / rows))

        out_band.FlushCache()
        out_ds = None
        feedback.pushInfo(f"Saved frequency raster at: {output_raster}")

        if load_result:
            rlayer = QgsRasterLayer(output_raster, os.path.basename(output_raster))
            if rlayer.isValid():
                QgsProject.instance().addMapLayer(rlayer)
                feedback.pushInfo("Loaded output raster into QGIS.")
            else:
                feedback.pushWarning("Output raster could not be loaded into QGIS.")

        return {self.OUTPUT_RASTER: output_raster}
