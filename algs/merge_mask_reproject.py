from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterFile,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterString,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterCrs,
    QgsVectorLayer,
    QgsCoordinateReferenceSystem,
    QgsProcessingException
)
import os
import re
from collections import defaultdict
import processing
from osgeo import gdal

class MergeMaskReprojectAlgorithm(QgsProcessingAlgorithm):
    INPUT_FOLDER = "INPUT_FOLDER"
    MASK_LAYER = "MASK_LAYER"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"
    MERGE_RASTERS = "MERGE_RASTERS"
    MERGE_PATTERN = "MERGE_PATTERN"
    TARGET_CRS = "TARGET_CRS"
    PREFIX = "PREFIX"

    def name(self):
        return "merge_mask_reproject"

    def displayName(self):
        return self.tr("Data preprocessing")

    def group(self):
        return self.tr('0_Raster preprocessing')

    def groupId(self):
        return 'raster_preprocessing'

    def shortHelpString(self):
        return self.tr(
            "Merges rasters based on a user-defined regex pattern, applies a vector mask, "
            "reprojects to a target CRS, and preserves the input subfolder structure.\n\n"
            "Regex pattern guide:\n"
            "**Merge (Optional):** If enabled, it merges raster files together based on a shared part of their filename. You define this shared part using a regex pattern.\n"
            "**Mask:** It clips all rasters using a vector mask layer.\n"
            "**Reproject:** It reprojects the rasters to a new Coordinate Reference System (CRS). If no CRS is chosen, it keeps the original.\n\n"
            "--- How to use the Regex Pattern ---\n"
            "The regex pattern identifies which files to merge. Simply define the part of the filename that is common to the files you want to group.\n\n"
            "Examples:\n"
            "   To merge date-based filenames: flood_2025-01-01_2025-01-10.tif\n"
            "   Regex could be: (flood_\\d{4}-\\d{2}-\\d{2}_\\d{4}-\\d{2}-\\d{2})\n"
            "   To merge numeric suffix filenames: flood_09876.tif, flood_09877.tif\n"
            "   Regex could be: (flood_\\d+)\n"
            "|   flood_ : Matches literal text 'flood_'   |   `\d` : Matches a single digit (0–9)|   |   `\d+`: Matches one or more digits   |   `\d{4}` : Matches exactly 4 digits (like a year)   |   `-` : Matches a literal hyphen   |\n"
        )

    def tr(self, string):
        return QCoreApplication.translate("MergeMaskReprojectAlgorithm", string)

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFile(
                self.INPUT_FOLDER,
                self.tr("Main input folder"),
                behavior=QgsProcessingParameterFile.Folder
            )
        )

        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.MASK_LAYER,
                self.tr("Vector mask layer"),
                [QgsProcessing.TypeVector]
            )
        )

        self.addParameter(
            QgsProcessingParameterFolderDestination(
                self.OUTPUT_FOLDER,
                self.tr("Output folder")
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.MERGE_RASTERS,
                self.tr("Merge rasters before masking"),
                defaultValue=False
            )
        )

        self.addParameter(
            QgsProcessingParameterString(
                self.MERGE_PATTERN,
                self.tr("Regex pattern to group rasters for merging"),
                optional=True,
                defaultValue="( )"
            )
        )

        self.addParameter(
            QgsProcessingParameterCrs(
                self.TARGET_CRS,
                self.tr("Target CRS"),
                optional=True
            )
        )

        self.addParameter(
            QgsProcessingParameterString(
                self.PREFIX,
                self.tr("Prefix for output rasters"),
                optional=True,
                defaultValue="mod_"
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        input_folder = self.parameterAsString(parameters, self.INPUT_FOLDER, context)
        mask_layer = self.parameterAsVectorLayer(parameters, self.MASK_LAYER, context)
        output_folder = self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)
        merge_rasters = self.parameterAsBool(parameters, self.MERGE_RASTERS, context)
        merge_pattern = self.parameterAsString(parameters, self.MERGE_PATTERN, context).strip()
        target_crs = self.parameterAsCrs(parameters, self.TARGET_CRS, context)
        prefix = self.parameterAsString(parameters, self.PREFIX, context)

        os.makedirs(output_folder, exist_ok=True)

        # Step 1: List all TIFFs
        all_files = []
        for root, _, files in os.walk(input_folder):
            for f in files:
                if f.lower().endswith(".tif"):
                    all_files.append(os.path.join(root, f))

        # Step 2: Group files for processing (merge or not)
        # The list will store tuples of: (filepath, base_name, relative_subfolder_path)
        files_to_process = []
        if merge_rasters:
            if not merge_pattern:
                raise QgsProcessingException("Please provide a regex pattern when merging is enabled.")
            pattern = re.compile(merge_pattern)
            grouped_files = defaultdict(list)
            for fpath in all_files:
                fname = os.path.basename(fpath)
                match = pattern.match(fname)
                if match:
                    base_name = match.group(1)
                    # Group by base_name and original directory
                    grouped_files[(base_name, os.path.dirname(fpath))].append(fpath)
            
            feedback.pushInfo(f"Found {len(grouped_files)} groups to merge.")

            for (base_name, folder), files in grouped_files.items():
                relative_subfolder = os.path.relpath(folder, input_folder)
                
                if len(files) < 2:
                    # Single file in a group, no merge needed, but carry it forward
                    files_to_process.append((files[0], base_name, relative_subfolder))
                    continue

                # Merge multiple files
                merged_path = processing.run("gdal:merge", {
                    'INPUT': files,
                    'SEPARATE': False,
                    'NODATA_INPUT': None,
                    'NODATA_OUTPUT': None,
                    'OPTIONS': 'COMPRESS=LZW',
                    'DATA_TYPE': None,
                    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                }, context=context, feedback=feedback)['OUTPUT']

                files_to_process.append((merged_path, base_name, relative_subfolder))
                feedback.pushInfo(f"Merged (temporary): {base_name}")
        else:
            # No merge, process all files individually
            for fpath in all_files:
                base_name = os.path.splitext(os.path.basename(fpath))[0]
                folder = os.path.dirname(fpath)
                relative_subfolder = os.path.relpath(folder, input_folder)
                files_to_process.append((fpath, base_name, relative_subfolder))

        # Step 3: Mask
        masked_files = []
        for fpath, base_name, relative_subfolder in files_to_process:
            if feedback.isCanceled():
                break
            
            masked_path = processing.run("gdal:cliprasterbymasklayer", {
                'INPUT': fpath,
                'MASK': mask_layer,
                'SOURCE_CRS': None,
                'TARGET_CRS': None,
                'TARGET_EXTENT': None,
                'NODATA': None,
                'ALPHA_BAND': False,
                'CROP_TO_CUTLINE': True,
                'KEEP_RESOLUTION': True,
                'SET_RESOLUTION': False,
                'X_RESOLUTION': None,
                'Y_RESOLUTION': None,
                'MULTITHREADING': False,
                'OPTIONS': 'COMPRESS=LZW',
                'DATA_TYPE': None,
                'EXTRA': '',
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
            }, context=context, feedback=feedback)['OUTPUT']
            
            masked_files.append((masked_path, base_name, relative_subfolder))
            feedback.pushInfo(f"Masked (temporary): {base_name}")

        # Step 4: Reproject and save to final location
        for fpath, base_name, relative_subfolder in masked_files:
            if feedback.isCanceled():
                break

            # Determine target CRS
            if not target_crs.isValid():
                ds = gdal.Open(fpath)
                wkt_crs = ds.GetProjection()
                ds = None
                if not wkt_crs:
                     feedback.pushWarning(f"Could not determine CRS for {base_name}. Skipping reprojection step but will still save.")
            else:
                wkt_crs = target_crs.toWkt()

            # Create the mirrored subfolder in the output directory
            output_subfolder = os.path.join(output_folder, relative_subfolder)
            if output_subfolder != output_folder: # Avoid creating '.' for root files
                os.makedirs(output_subfolder, exist_ok=True)
            
            # Define the final output path within the subfolder
            final_path = os.path.join(output_subfolder, f"{prefix}{base_name}.tif")

            processing.run("gdal:warpreproject", {
                'INPUT': fpath,
                'SOURCE_CRS': None, # Source CRS is read from the temp file
                'TARGET_CRS': wkt_crs,
                'RESAMPLING': 0, # Nearest Neighbour
                'NODATA': None,
                'TARGET_RESOLUTION': None,
                'OPTIONS': 'COMPRESS=LZW',
                'DATA_TYPE': None, # Keep original data type
                'TARGET_EXTENT': None,
                'TARGET_EXTENT_CRS': None,
                'MULTITHREADING': True,
                'OUTPUT': final_path
            }, context=context, feedback=feedback)

            feedback.pushInfo(f"Reprojected and saved: {final_path}")

        return {self.OUTPUT_FOLDER: output_folder}

    def createInstance(self):
        return MergeMaskReprojectAlgorithm()
        
    def icon(self):
            plugin_dir = os.path.dirname(__file__)
            icon_path = os.path.join(plugin_dir, "icons", "preprocess_icon.jpeg")
            return QIcon(icon_path)