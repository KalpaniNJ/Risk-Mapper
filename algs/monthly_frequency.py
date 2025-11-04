import os
import re
import numpy as np
from collections import defaultdict
from osgeo import gdal
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterFile,
    QgsProcessingParameterString,
    QgsProcessingParameterBoolean,
    QgsRasterLayer,
    QgsProject
)

class MonthlyFrequencyAlgorithm(QgsProcessingAlgorithm):
    """
    Generate monthly frequency maps from subfolders.
    Assumes raster filenames follow the YYYY-MM-DD convention.
    """

    INPUT_FOLDER = "INPUT_FOLDER"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"
    PREFIX = "PREFIX"
    LOAD_MAPS = "LOAD_MAPS"

    def initAlgorithm(self, config=None):
        # Input folder
        self.addParameter(
            QgsProcessingParameterFile(
                self.INPUT_FOLDER,
                "Main input folder",
                behavior=QgsProcessingParameterFile.Folder
            )
        )

        # Output folder
        self.addParameter(
            QgsProcessingParameterFolderDestination(
                self.OUTPUT_FOLDER,
                "Output folder"
            )
        )

        # Prefix
        self.addParameter(
            QgsProcessingParameterString(
                self.PREFIX,
                "Prefix",
                defaultValue="frequencymaps_"
            )
        )

        # Option to load maps into QGIS
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.LOAD_MAPS,
                "Load layers on completion",
                defaultValue=True
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        main_input_folder = self.parameterAsFile(parameters, self.INPUT_FOLDER, context)
        output_base_folder = self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)
        prefix = self.parameterAsString(parameters, self.PREFIX, context)
        load_maps = self.parameterAsBool(parameters, self.LOAD_MAPS, context)

        block_size = 512
        os.makedirs(output_base_folder, exist_ok=True)

        rasters_by_month = defaultdict(list)
        month_pattern = r"\d{4}-(\d{2})-\d{2}"  # extract month from YYYY-MM-DD

        # Traverse all subfolders recursively
        for root, dirs, files in os.walk(main_input_folder):
            for fname in files:
                if fname.lower().endswith('.tif'):
                    match = re.search(month_pattern, fname)
                    if match:
                        month = match.group(1)
                        full_path = os.path.join(root, fname)
                        rasters_by_month[month].append(full_path)
                        feedback.pushInfo(f"{fname} → month {month}")
                    else:
                        feedback.pushInfo(f"Skipping file (does not match YYYY-MM-DD): {fname}")

        # Process each month
        for month, rasters in sorted(rasters_by_month.items()):
            if len(rasters) == 0:
                continue

            feedback.pushInfo(f"Processing month {month} with {len(rasters)} rasters...")

            ds = gdal.Open(rasters[0])
            geo = ds.GetGeoTransform()
            proj = ds.GetProjection()
            cols = ds.RasterXSize
            rows = ds.RasterYSize
            band = ds.GetRasterBand(1)
            nodata = band.GetNoDataValue()
            ds = None

            output_path = os.path.join(output_base_folder, f'{prefix}{month}.tif')
            driver = gdal.GetDriverByName('GTiff')
            out_ds = driver.Create(output_path, cols, rows, 1, gdal.GDT_Float32, options=['COMPRESS=LZW'])
            out_ds.SetGeoTransform(geo)
            out_ds.SetProjection(proj)
            out_band = out_ds.GetRasterBand(1)
            out_band.SetNoDataValue(0)

            for y in range(0, rows, block_size):
                rows_to_read = min(block_size, rows - y)
                for x in range(0, cols, block_size):
                    cols_to_read = min(block_size, cols - x)
                    block_sum = np.zeros((rows_to_read, cols_to_read), dtype=np.float32)

                    for r in rasters:
                        ds = gdal.Open(r)
                        band = ds.GetRasterBand(1)
                        data = band.ReadAsArray(x, y, cols_to_read, rows_to_read).astype(np.float32)
                        nd = band.GetNoDataValue()
                        if nd is not None:
                            data[data == nd] = 0
                        block_sum += data
                        ds = None

                    out_band.WriteArray(block_sum, xoff=x, yoff=y)

            out_ds.FlushCache()
            out_ds = None
            feedback.pushInfo(f"Saved: {output_path}")

            # Automatically load map into QGIS
            if load_maps:
                rlayer = QgsRasterLayer(output_path, f"{prefix}{month}")
                if rlayer.isValid():
                    QgsProject.instance().addMapLayer(rlayer)
                    feedback.pushInfo(f"Loaded {output_path}")
                else:
                    feedback.pushInfo(f"Failed to load {output_path}")

        feedback.pushInfo("All monthly frequency maps created successfully.")
        return {self.OUTPUT_FOLDER: output_base_folder}

    def name(self):
        return "monthlyfrequency"

    def displayName(self):
        return "Monthly frequency maps"

    def group(self):
        return "1_Hazard analysis"

    def groupId(self):
        return "hazard_analysis"

    def createInstance(self):
        return MonthlyFrequencyAlgorithm()
        
    def icon(self):
            plugin_dir = os.path.dirname(__file__)
            icon_path = os.path.join(plugin_dir, "icons", "mnfreq_icon.jpeg")
            return QIcon(icon_path)
