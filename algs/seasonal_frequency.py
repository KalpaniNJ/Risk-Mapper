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
    QgsProcessingParameterMatrix,
    QgsRasterLayer,
    QgsProject
)
from qgis.PyQt.QtCore import QCoreApplication

class SeasonalFrequencyAlgorithm(QgsProcessingAlgorithm):
    """
    Generate seasonal frequency maps from subfolders.
    Correctly handles consecutive months spanning years
    and fills missing months with zeros.
    """

    INPUT_FOLDER = "INPUT_FOLDER"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"
    PREFIX = "PREFIX"
    LOAD_MAPS = "LOAD_MAPS"
    SEASONS = "SEASONS"

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return SeasonalFrequencyAlgorithm()
        
    def icon(self):
            plugin_dir = os.path.dirname(__file__)
            icon_path = os.path.join(plugin_dir, "icons", "sn_icon.jpeg")
            return QIcon(icon_path)

    def name(self):
        return "seasonalfrequency"

    def displayName(self):
        return self.tr("Seasonal frequency maps")

    def group(self):
        return self.tr("1_Hazard analysis")

    def groupId(self):
        return "hazard_analysis"

    def shortHelpString(self):
        return self.tr(
            "Generates seasonal frequency maps from input rasters. "
            "Seasons are defined by the user in a table. Consecutive months spanning years are handled correctly, "
            "and missing months are filled with zeros."
        )

    def initAlgorithm(self, config=None):
        # Input folder
        self.addParameter(
            QgsProcessingParameterFile(
                self.INPUT_FOLDER,
                self.tr("Main input folder"),
                behavior=QgsProcessingParameterFile.Folder
            )
        )

        # Output folder
        self.addParameter(
            QgsProcessingParameterFolderDestination(
                self.OUTPUT_FOLDER,
                self.tr("Output folder")
            )
        )

        # Prefix
        self.addParameter(
            QgsProcessingParameterString(
                self.PREFIX,
                self.tr("Prefix"),
                defaultValue="frequencymaps_"
            )
        )

        # Load maps into QGIS
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.LOAD_MAPS,
                self.tr("Load layers on completion"),
                defaultValue=True
            )
        )

        # Seasons table (season name + months in order)
        self.addParameter(
            QgsProcessingParameterMatrix(
                self.SEASONS,
                self.tr("Seasons Definition"),
                headers=[self.tr("Season Name"), self.tr("Months (comma-separated, e.g. 11,12,01,02)")],
                numberRows=3
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        input_folder = self.parameterAsFile(parameters, self.INPUT_FOLDER, context)
        output_folder = self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)
        prefix = self.parameterAsString(parameters, self.PREFIX, context)
        load_maps = self.parameterAsBool(parameters, self.LOAD_MAPS, context)
        seasons_matrix = self.parameterAsMatrix(parameters, self.SEASONS, context)

        block_size = 512
        os.makedirs(output_folder, exist_ok=True)

        # Convert matrix to dictionary {season_name: [month sequence]}
        seasons = {}
        for i in range(0, len(seasons_matrix), 2):
            season_name = seasons_matrix[i]
            months_str = seasons_matrix[i + 1]
            if not season_name or not months_str:
                continue
            months = [m.strip().zfill(2) for m in months_str.split(',')]
            seasons[season_name] = months
        feedback.pushInfo(f"Using {len(seasons)} user-defined seasons: {seasons}")

        # Function to extract year and month from filename
        def extract_year_month(filename):
            match = re.search(r"(\d{4})-(\d{2})-\d{2}", filename)
            if match:
                return int(match.group(1)), match.group(2)
            return None, None

        # Collect all rasters with year and month
        rasters = []
        for root, dirs, files in os.walk(input_folder):
            for fname in files:
                if not fname.lower().endswith(".tif"):
                    continue
                year, month = extract_year_month(fname)
                if not year or not month:
                    feedback.pushWarning(f"Skipping file with bad name: {fname}")
                    continue
                rasters.append((year, month, os.path.join(root, fname)))

        # Sort rasters by year, month
        rasters.sort(key=lambda x: (x[0], int(x[1])))

        # Build mapping of rasters to season-year
        season_raster_map = defaultdict(list)
        for season_name, season_months in seasons.items():
            first_month = int(season_months[0])  # first month defined by user
            for y, m, f in rasters:
                m_int = int(m)
                if m in season_months:
                    # Decide season year
                    if m_int >= first_month:
                        season_year = y
                    else:
                        season_year = y - 1
                    season_raster_map[(season_year, season_name)].append((y, m, f))

        results = []

        # Process each season-year
        for (season_year, season_name), month_files in sorted(season_raster_map.items()):
            if not month_files:
                continue

            # Prepare final file list matching season month order, filling None for missing months
            final_files = []
            month_year_list = []
            for m in seasons[season_name]:
                match = next(((y, f) for y, mon, f in month_files if mon == m), None)
                if match:
                    y, f = match
                    final_files.append(f)
                    month_year_list.append(f"{m}({y}->{season_year})")
                else:
                    final_files.append(None)
                    month_year_list.append(f"{m}(--->{season_year})")

            feedback.pushInfo(f"Processing {season_name} in {season_year} with {len(month_files)} rasters...")
            feedback.pushInfo(f"Months with original->adjusted year: {', '.join(month_year_list)}")

            # Get metadata from the first available raster
            for f in final_files:
                if f:
                    ds = gdal.Open(f)
                    geo = ds.GetGeoTransform()
                    proj = ds.GetProjection()
                    cols = ds.RasterXSize
                    rows = ds.RasterYSize
                    ds = None
                    break

            # Output path
            out_path = os.path.join(output_folder, f"{prefix}{season_year}_{season_name}.tif")
            driver = gdal.GetDriverByName("GTiff")
            out_ds = driver.Create(out_path, cols, rows, 1, gdal.GDT_Float32, options=['COMPRESS=LZW'])
            out_ds.SetGeoTransform(geo)
            out_ds.SetProjection(proj)
            out_band = out_ds.GetRasterBand(1)
            out_band.SetNoDataValue(0)

            # Block-wise summing
            for y in range(0, rows, block_size):
                rows_to_read = min(block_size, rows - y)
                for x in range(0, cols, block_size):
                    cols_to_read = min(block_size, cols - x)
                    block_sum = np.zeros((rows_to_read, cols_to_read), dtype=np.float32)

                    for tif_path in final_files:
                        if tif_path:
                            ds = gdal.Open(tif_path)
                            band = ds.GetRasterBand(1)
                            data = band.ReadAsArray(x, y, cols_to_read, rows_to_read).astype(np.float32)
                            nd = band.GetNoDataValue()
                            if nd is not None:
                                data[data == nd] = 0
                            block_sum += data
                            ds = None
                        else:
                            # Missing month → add zeros
                            block_sum += 0

                    out_band.WriteArray(block_sum, xoff=x, yoff=y)

            out_ds.FlushCache()
            out_ds = None
            results.append(out_path)
            feedback.pushInfo(f"Saved: {out_path}")

            # Auto-load into QGIS
            if load_maps:
                rlayer = QgsRasterLayer(out_path, f"{prefix}{season_year}_{season_name}")
                if rlayer.isValid():
                    QgsProject.instance().addMapLayer(rlayer)
                    feedback.pushInfo(f"Loaded {out_path}")
                else:
                    feedback.pushWarning(f"Failed to load {out_path}")

        feedback.pushInfo("All seasonal frequency maps created successfully.")
        return {self.OUTPUT_FOLDER: results}
