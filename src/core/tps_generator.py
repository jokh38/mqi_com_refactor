# =====================================================================================
# Target File: src/core/tps_generator.py
# Source Reference: Legacy TPS Generator service
# =====================================================================================

from pathlib import Path
from typing import Dict, Any, Optional
import re

from src.config.settings import Settings
from src.infrastructure.logging_handler import StructuredLogger


class TpsGenerator:
    """
    Service for generating dynamic moqui_tps.in configuration files for cases.
    
    This service replaces the static input.mqi dependency by generating case-specific
    configuration files at runtime based on parameters from config.yaml and dynamic
    case data such as GPU allocation and file paths.
    """
    
    def __init__(self, settings: Settings, logger: StructuredLogger):
        """
        Initialize TPS generator with configuration settings and logger.
        
        Args:
            settings: Application settings containing moqui_tps_parameters
            logger: Structured logger for error reporting and debugging
        """
        self.settings = settings
        self.logger = logger
        self.base_parameters = settings.get_moqui_tps_parameters()
        
    def generate_tps_file(
        self,
        case_path: Path,
        case_id: str,
        gpu_id: int,
        execution_mode: str = "local"
    ) -> bool:
        """
        Generate moqui_tps.in file for a specific case.
        
        Args:
            case_path: Path to the case directory
            case_id: Unique identifier for the case
            gpu_id: GPU ID to be assigned for this case (0, 1, 2, etc.)
            execution_mode: "local" or "remote" - determines path construction
            
        Returns:
            True if file was generated successfully, False otherwise
        """
        try:
            self.logger.info("Generating moqui_tps.in file", {
                "case_id": case_id,
                "case_path": str(case_path),
                "gpu_id": gpu_id,
                "execution_mode": execution_mode
            })
            
            # Start with base parameters from config
            parameters = self.base_parameters.copy()
            
            # Set dynamic GPU ID
            parameters["GPUID"] = gpu_id
            
            # Generate dynamic paths based on execution mode
            dynamic_paths = self._generate_dynamic_paths(case_path, case_id, execution_mode)
            parameters.update(dynamic_paths)
            
            # Extract case-specific data (e.g., beam numbers from DICOM)
            case_specific_data = self._extract_case_data(case_path, case_id)
            parameters.update(case_specific_data)
            
            # Validate required parameters
            if not self._validate_parameters(parameters, case_id):
                return False
                
            # Generate and write the file
            content = self._format_parameters_to_string(parameters)
            output_file = case_path / "moqui_tps.in"
            
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(content)
                
            self.logger.info("moqui_tps.in file generated successfully", {
                "case_id": case_id,
                "output_file": str(output_file),
                "parameters_count": len(parameters)
            })
            
            return True
            
        except Exception as e:
            self.logger.error("Failed to generate moqui_tps.in file", {
                "case_id": case_id,
                "case_path": str(case_path),
                "error": str(e),
                "exception_type": type(e).__name__
            })
            return False
    
    def _generate_dynamic_paths(
        self,
        case_path: Path,
        case_id: str,
        execution_mode: str
    ) -> Dict[str, Any]:
        """
        Generate dynamic file paths based on execution mode.
        
        Args:
            case_path: Path to the case directory  
            case_id: Unique identifier for the case
            execution_mode: "local" or "remote" execution mode
            
        Returns:
            Dictionary containing dynamic path parameters
        """
        paths = {}
        
        if execution_mode == "remote":
            # Use HPC paths from config
            hpc_paths = self.settings.get_hpc_paths()
            base_dir = hpc_paths.get('base_dir', '/home/gpuadmin/MOQUI_SMC')
            
            paths.update({
                "DicomDir": str(case_path),  # Local path for DICOM files
                "OutputDir": f"{base_dir}/Dose_raw/{case_id}",
                "logFilePath": f"{base_dir}/Dose_raw/{case_id}/simulation.log",
                "ParentDir": f"{base_dir}/Output_csv/{case_id}"
            })
            
        else:
            # Use local paths for local execution
            case_directories = self.settings.get_case_directories()
            
            paths.update({
                "DicomDir": str(case_path),
                "OutputDir": str(case_path / "raw_output"),
                "logFilePath": str(case_path / "simulation.log"),
                "ParentDir": str(case_path / "csv_output")
            })
            
        return paths
    
    def _extract_case_data(self, case_path: Path, case_id: str) -> Dict[str, Any]:
        """
        Extract case-specific data from DICOM files or other sources.
        
        Args:
            case_path: Path to the case directory
            case_id: Unique identifier for the case
            
        Returns:
            Dictionary containing case-specific parameters
        """
        case_data = {}
        
        try:
            # Look for beam number information in DICOM files or metadata
            # For now, use default value but this could be enhanced to read DICOM metadata
            beam_count = self._count_treatment_beams(case_path)
            if beam_count > 0:
                case_data["BeamNumbers"] = beam_count
                case_data["GantryNum"] = beam_count  # Often the same as beam count
                
            self.logger.debug("Extracted case-specific data", {
                "case_id": case_id,
                "beam_count": beam_count,
                "case_data": case_data
            })
            
        except Exception as e:
            self.logger.warning("Could not extract case-specific data, using defaults", {
                "case_id": case_id,
                "error": str(e)
            })
            
        return case_data
    
    def _count_treatment_beams(self, case_path: Path) -> int:
        """
        Count the number of treatment beams from DICOM files or metadata.
        
        This is a simplified implementation that could be enhanced to parse
        DICOM files properly using pydicom or similar libraries.
        
        Args:
            case_path: Path to the case directory
            
        Returns:
            Number of treatment beams (default to 1 if cannot determine)
        """
        try:
            # Look for DICOM files
            dicom_files = list(case_path.glob("*.dcm")) + list(case_path.glob("**/*.dcm"))
            
            # Simple heuristic: if multiple DICOM files, assume multiple beams
            # This could be replaced with proper DICOM parsing
            if len(dicom_files) > 1:
                return len(dicom_files)
            elif len(dicom_files) == 1:
                return 1
            else:
                # No DICOM files found, default to 1 beam
                # Future enhancement could look for other metadata sources
                return 1
                
        except Exception as e:
            self.logger.debug("Error counting treatment beams, defaulting to 1", {
                "case_path": str(case_path),
                "error": str(e)
            })
            return 1
    
    def _validate_parameters(self, parameters: Dict[str, Any], case_id: str) -> bool:
        """
        Validate that all required parameters are present and valid.
        
        Args:
            parameters: Dictionary of parameters to validate
            case_id: Case ID for logging context
            
        Returns:
            True if validation passes, False otherwise
        """
        try:
            # Get required parameters from config
            tps_config = self.settings._yaml_config.get('tps_generator', {})
            validation_config = tps_config.get('validation', {})
            required_params = validation_config.get('required_params', [])
            
            if not required_params:
                # Default required parameters if not configured
                required_params = ['GPUID', 'DicomDir', 'logFilePath', 'OutputDir']
            
            missing_params = []
            empty_params = []
            
            for param in required_params:
                if param not in parameters:
                    missing_params.append(param)
                elif not parameters[param] and parameters[param] != 0:  # Allow GPUID=0
                    empty_params.append(param)
            
            if missing_params or empty_params:
                self.logger.error("TPS parameter validation failed", {
                    "case_id": case_id,
                    "missing_params": missing_params,
                    "empty_params": empty_params
                })
                return False
                
            self.logger.debug("TPS parameter validation passed", {
                "case_id": case_id,
                "validated_params": list(parameters.keys())
            })
            
            return True
            
        except Exception as e:
            self.logger.error("Error during parameter validation", {
                "case_id": case_id,
                "error": str(e)
            })
            return False
    
    def _format_parameters_to_string(self, parameters: Dict[str, Any]) -> str:
        """
        Format parameters dictionary into the moqui_tps.in file format.
        
        The format is: key value\n for each parameter.
        
        Args:
            parameters: Dictionary of parameters
            
        Returns:
            Formatted string content for the file
        """
        lines = []
        
        # Sort parameters for consistent output
        sorted_params = sorted(parameters.items())
        
        for key, value in sorted_params:
            # Format value appropriately
            if isinstance(value, bool):
                formatted_value = "true" if value else "false"
            elif isinstance(value, (int, float)):
                formatted_value = str(value)
            else:
                formatted_value = str(value)
                
            lines.append(f"{key} {formatted_value}")
            
        # Add final newline
        content = "\n".join(lines) + "\n"
        
        return content