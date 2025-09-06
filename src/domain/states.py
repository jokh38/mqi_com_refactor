# =====================================================================================
# Target File: src/domain/states.py
# Source Reference: src/states.py
# =====================================================================================

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.core.workflow_manager import WorkflowManager

from src.domain.enums import CaseStatus, WorkflowStep
from src.domain.errors import ProcessingError
from pathlib import Path


class WorkflowState(ABC):
    """
    Abstract base class for workflow states implementing the State pattern.
    FROM: Migrated from original states.py state machine implementation.
    """

    @abstractmethod
    def execute(self, context: 'WorkflowManager') -> Optional[WorkflowState]:
        """
        Execute the current state and return the next state.
        
        Args:
            context: The workflow manager providing access to repositories and handlers
            
        Returns:
            The next state to transition to, or None to terminate.
        """
        pass

    @abstractmethod
    def get_state_name(self) -> str:
        """Return the human-readable name of this state."""
        pass

class InitialState(WorkflowState):
    """
    Initial state for new cases - validates case structure and dynamically generates moqui_tps.in.
    FROM: Initial state logic from original states.py, modified to generate TPS file directly.
    """

    def execute(self, context: 'WorkflowManager') -> WorkflowState:
        """
        Perform initial validation and generate moqui_tps.in file.
        FROM: Modified from original validation logic to include TPS generation.
        """
        context.logger.info("Performing initial validation and moqui_tps.in generation", {
            "case_id": context.case_id,
            "case_path": str(context.case_path)
        })
        
        # Update case status
        context.case_repo.update_case_status(context.case_id, CaseStatus.PREPROCESSING)
        
        # Validate case directory structure
        if not context.case_path.is_dir():
            error_msg = f"Case path is not a valid directory: {context.case_path}"
            context.logger.error(error_msg, {"case_id": context.case_id})
            context.case_repo.update_case_status(context.case_id, CaseStatus.FAILED)
            return FailedState()
        
        # Generate moqui_tps.in configuration file
        try:
            context.logger.info("Generating moqui_tps.in configuration file", {
                "case_id": context.case_id
            })
            
            # Get GPU allocation for the case to determine GPU ID
            gpu_allocation = context.gpu_repo.find_and_lock_available_gpu(context.case_id)
            if not gpu_allocation:
                error_msg = "No GPU available for TPS generation"
                context.logger.error(error_msg, {"case_id": context.case_id})
                context.case_repo.update_case_status(context.case_id, CaseStatus.FAILED)
                return FailedState()
            
            # Extract GPU ID from UUID (simplified approach)
            gpu_id = 0  # Default to 0, could be enhanced to parse from allocation
            
            # Generate the TPS file
            success = context.tps_generator.generate_tps_file(
                case_path=context.case_path,
                case_id=context.case_id,
                gpu_id=gpu_id,
                execution_mode="remote"  # or "local" based on configuration
            )
            
            # Release GPU allocation after generating config
            context.gpu_repo.release_gpu(gpu_allocation['gpu_uuid'])
            
            if not success:
                error_msg = "Failed to generate moqui_tps.in file"
                context.logger.error(error_msg, {"case_id": context.case_id})
                context.case_repo.update_case_status(context.case_id, CaseStatus.FAILED)
                return FailedState()
            
            # Verify the file was created
            tps_file = context.case_path / "moqui_tps.in"
            if not tps_file.exists():
                error_msg = "Generated moqui_tps.in file not found"
                context.logger.error(error_msg, {
                    "case_id": context.case_id,
                    "expected_file": str(tps_file)
                })
                context.case_repo.update_case_status(context.case_id, CaseStatus.FAILED)
                return FailedState()
            
            # Record workflow step
            context.case_repo.record_workflow_step(
                case_id=context.case_id,
                step=WorkflowStep.TPS_GENERATION,
                status="completed",
                error_message="TPS configuration file generated successfully"
            )
            
            context.logger.info("Initial validation and TPS generation completed successfully", {
                "case_id": context.case_id,
                "tps_file": str(tps_file)
            })
            
            return PreprocessingState()
            
        except Exception as e:
            # Make sure to release GPU on any error
            if 'gpu_allocation' in locals() and gpu_allocation:
                context.gpu_repo.release_gpu(gpu_allocation['gpu_uuid'])
                
            error_msg = f"Initial state error: {str(e)}"
            context.logger.error(error_msg, {
                "case_id": context.case_id,
                "exception_type": type(e).__name__
            })
            context.case_repo.update_case_status(context.case_id, CaseStatus.FAILED)
            return FailedState()

    def get_state_name(self) -> str:
        return "Initial Validation"


class PreprocessingState(WorkflowState):
    """
    Preprocessing state - runs mqi_interpreter locally (P2 process).
    FROM: Preprocessing state from original states.py.
    """

    def execute(self, context: 'WorkflowManager') -> WorkflowState:
        """
        Execute local preprocessing using mqi_interpreter for each beam subdirectory.
        FROM: Refactored preprocessing logic to process individual beam directories.
        """
        context.logger.info("Running mqi_interpreter preprocessing for beam subdirectories", {
            "case_id": context.case_id
        })
        
        try:
            # Step 1: Identify beam subdirectories
            beam_paths = [d for d in context.case_path.iterdir() if d.is_dir()]
            
            # Step 2: Pre-computation checks
            if not beam_paths:
                error_msg = "No beam subdirectories found in case directory"
                context.logger.error(error_msg, {
                    "case_id": context.case_id,
                    "case_path": str(context.case_path)
                })
                context.case_repo.update_case_status(context.case_id, CaseStatus.FAILED)
                return FailedState()
            
            context.logger.info(f"Found {len(beam_paths)} beam subdirectories to process", {
                "case_id": context.case_id,
                "beam_count": len(beam_paths),
                "beam_names": [beam.name for beam in beam_paths]
            })
            
            # Get processing directory for CSV output (shared for entire case)
            case_dirs = context.local_handler.settings.get_case_directories()
            processing_dir = str(case_dirs['processing']).format(
                case_id=context.case_id,
                base_directory=context.local_handler.settings.get_base_directory()
            )
            processing_path = Path(processing_dir)
            
            # Ensure processing directory exists
            processing_path.mkdir(parents=True, exist_ok=True)
            
            # The input file is located in the parent case directory
            input_file = context.case_path / "moqui_tps.in"
            if not input_file.exists():
                error_msg = f"moqui_tps.in file not found: {input_file}"
                context.logger.error(error_msg, {
                    "case_id": context.case_id,
                    "input_file": str(input_file)
                })
                context.case_repo.update_case_status(context.case_id, CaseStatus.FAILED)
                return FailedState()
            
            # Step 3: Iterate and execute for each beam directory
            beams_processed = 0
            for beam_path in beam_paths:
                context.logger.info(f"Interpreting beam: {beam_path.name}", {
                    "case_id": context.case_id,
                    "beam_name": beam_path.name,
                    "beam_path": str(beam_path)
                })
                
                # Step 4: Execute mqi_interpreter with current beam_path
                result = context.local_handler.run_mqi_interpreter(
                    beam_directory=beam_path,  # Pass the individual beam directory
                    output_dir=processing_path
                )
                
                # Step 4: Robust error handling for individual beam
                if not result.success:
                    error_msg = f"mqi_interpreter failed for beam '{beam_path.name}'. Error: {result.error}"
                    context.logger.error(error_msg, {
                        "case_id": context.case_id,
                        "beam_name": beam_path.name,
                        "beam_path": str(beam_path),
                        "command_output": result.output,
                        "stderr": result.error
                    })
                    context.case_repo.update_case_status(context.case_id, CaseStatus.FAILED)
                    return FailedState()
                
                beams_processed += 1
                context.logger.info(f"Successfully processed beam: {beam_path.name}", {
                    "case_id": context.case_id,
                    "beam_name": beam_path.name,
                    "beams_processed": beams_processed,
                    "total_beams": len(beam_paths)
                })
            
            # Step 5: Verify collective success
            csv_files = list(processing_path.glob("*.csv"))
            if not csv_files:
                error_msg = "No CSV files generated after processing all beams"
                context.logger.error(error_msg, {
                    "case_id": context.case_id,
                    "processing_dir": str(processing_path),
                    "beams_processed": beams_processed
                })
                context.case_repo.update_case_status(context.case_id, CaseStatus.FAILED)
                return FailedState()
                
            context.logger.info("Preprocessing completed successfully for all beams", {
                "case_id": context.case_id,
                "processing_dir": str(processing_path),
                "csv_files_count": len(csv_files),
                "beams_processed": beams_processed
            })
            
            return FileUploadState()
            
        except Exception as e:
            error_msg = f"Preprocessing error: {str(e)}"
            context.logger.error(error_msg, {
                "case_id": context.case_id,
                "exception_type": type(e).__name__
            })
            context.case_repo.update_case_status(context.case_id, CaseStatus.FAILED)
            return FailedState()

    def get_state_name(self) -> str:
        return "Preprocessing"

class FileUploadState(WorkflowState):
    """
    File upload state - uploads files to HPC via SFTP with differentiated upload paths.
    FROM: FileUploadState from original states.py.
    REFACTORED: Now uploads TPS file and CSV files to separate directories per refactor_execute.md
    """

    def execute(self, context: 'WorkflowManager') -> WorkflowState:
        """
        Upload case files to HPC cluster via SFTP with differentiated paths.
        FROM: File upload logic from original workflow.
        REFACTORED: Separated TPS and CSV file uploads to different remote directories.
        """
        context.logger.info("Uploading files to HPC cluster with differentiated paths", {
            "case_id": context.case_id
        })
        
        try:
            # Get HPC paths from configuration
            hpc_paths = context.local_handler.settings.get_hpc_paths()
            if not hpc_paths:
                error_msg = "HPC paths configuration not found"
                context.logger.error(error_msg, {"case_id": context.case_id})
                context.case_repo.update_case_status(context.case_id, CaseStatus.FAILED)
                return FailedState()
            
            tps_env_dir = hpc_paths.get('tps_env_dir')
            output_csv_dir = hpc_paths.get('output_csv_dir')
            
            if not tps_env_dir or not output_csv_dir:
                error_msg = "Required HPC paths (tps_env_dir, output_csv_dir) not configured"
                context.logger.error(error_msg, {"case_id": context.case_id})
                context.case_repo.update_case_status(context.case_id, CaseStatus.FAILED)
                return FailedState()
            
            # Format the remote CSV directory path with case_id
            remote_csv_path = output_csv_dir.format(case_id=context.case_id)
            
            # Step 1: Upload moqui_tps.in file to tps_env_dir
            success = self._upload_tps_file(context, tps_env_dir)
            if not success:
                return FailedState()
            
            # Step 2: Upload CSV files to formatted remote CSV directory
            success = self._upload_csv_files(context, remote_csv_path)
            if not success:
                return FailedState()
            
            # Store remote CSV path in context for HpcExecutionState
            context.remote_csv_path = remote_csv_path
            
            context.logger.info("File upload completed successfully with differentiated paths", {
                "case_id": context.case_id,
                "tps_dir": tps_env_dir,
                "csv_dir": remote_csv_path
            })
            
            return HpcExecutionState()
            
        except Exception as e:
            error_msg = f"File upload error: {str(e)}"
            context.logger.error(error_msg, {
                "case_id": context.case_id,
                "exception_type": type(e).__name__
            })
            context.case_repo.update_case_status(context.case_id, CaseStatus.FAILED)
            return FailedState()

    def _upload_tps_file(self, context: 'WorkflowManager', tps_env_dir: str) -> bool:
        """
        Upload moqui_tps.in file to the TPS environment directory.
        
        Args:
            context: Workflow manager context
            tps_env_dir: Remote TPS environment directory
            
        Returns:
            True if upload successful, False otherwise
        """
        tps_file = context.case_path / "moqui_tps.in"
        if not tps_file.exists():
            error_msg = "moqui_tps.in file not found"
            context.logger.error(error_msg, {
                "case_id": context.case_id,
                "tps_file": str(tps_file)
            })
            context.case_repo.update_case_status(context.case_id, CaseStatus.FAILED)
            return False
        
        result = context.remote_handler.upload_file(
            local_file=tps_file,
            remote_dir=tps_env_dir
        )
        
        if not result.success:
            error_msg = f"Failed to upload moqui_tps.in to {tps_env_dir}: {result.error}"
            context.logger.error(error_msg, {
                "case_id": context.case_id,
                "file_name": "moqui_tps.in",
                "tps_env_dir": tps_env_dir
            })
            context.case_repo.update_case_status(context.case_id, CaseStatus.FAILED)
            return False
            
        context.logger.info("Successfully uploaded moqui_tps.in", {
            "case_id": context.case_id,
            "tps_env_dir": tps_env_dir
        })
        return True

    def _upload_csv_files(self, context: 'WorkflowManager', remote_csv_path: str) -> bool:
        """
        Upload all CSV files to the remote CSV directory.
        
        Args:
            context: Workflow manager context
            remote_csv_path: Remote directory path for CSV files
            
        Returns:
            True if upload successful, False otherwise
        """
        # Get processing directory path for CSV files
        case_dirs = context.local_handler.settings.get_case_directories()
        processing_dir = str(case_dirs['processing']).format(
            case_id=context.case_id,
            base_directory=context.local_handler.settings.get_base_directory()
        )
        processing_path = Path(processing_dir)
        
        if not processing_path.exists() or not processing_path.is_dir():
            error_msg = "CSV processing directory not found"
            context.logger.error(error_msg, {
                "case_id": context.case_id,
                "processing_dir": str(processing_path)
            })
            context.case_repo.update_case_status(context.case_id, CaseStatus.FAILED)
            return False
        
        csv_files = list(processing_path.glob("*.csv"))
        if not csv_files:
            error_msg = "No CSV files found in processing directory"
            context.logger.error(error_msg, {
                "case_id": context.case_id,
                "processing_dir": str(processing_path)
            })
            context.case_repo.update_case_status(context.case_id, CaseStatus.FAILED)
            return False
        
        # Upload each CSV file to the remote CSV directory
        for csv_file in csv_files:
            result = context.remote_handler.upload_file(
                local_file=csv_file,
                remote_dir=remote_csv_path
            )
            if not result.success:
                error_msg = f"Failed to upload CSV file {csv_file.name}: {result.error}"
                context.logger.error(error_msg, {
                    "case_id": context.case_id,
                    "csv_file": str(csv_file),
                    "remote_csv_path": remote_csv_path
                })
                context.case_repo.update_case_status(context.case_id, CaseStatus.FAILED)
                return False
                
        context.logger.info(f"Successfully uploaded {len(csv_files)} CSV files", {
            "case_id": context.case_id,
            "csv_files_count": len(csv_files),
            "remote_csv_path": remote_csv_path
        })
        return True

    def get_state_name(self) -> str:
        return "File Upload"


class HpcExecutionState(WorkflowState):
    """
    HPC execution state - runs MOQUI simulation on HPC via SSH.
    FROM: HpcExecutionState from original states.py.
    """

    def execute(self, context: 'WorkflowManager') -> WorkflowState:
        """
        Execute MOQUI simulation on HPC and poll for completion.
        FROM: HPC execution logic from original workflow.
        """
        context.logger.info("Starting HPC simulation execution", {
            "case_id": context.case_id
        })
        
        # Update status to processing
        context.case_repo.update_case_status(context.case_id, CaseStatus.PROCESSING)
        
        try:
            # Allocate GPU for the job
            gpu_allocation = context.gpu_repo.find_and_lock_available_gpu(context.case_id)
            if not gpu_allocation:
                error_msg = "No GPU available for simulation"
                context.logger.error(error_msg, {"case_id": context.case_id})
                context.case_repo.update_case_status(context.case_id, CaseStatus.FAILED)
                return FailedState()
            
            context.logger.info("GPU allocated for simulation", {
                "case_id": context.case_id,
                "gpu_uuid": gpu_allocation.gpu_uuid
            })
            
            # Submit simulation job to HPC with dynamic CSV path
            remote_case_dir = f"/tmp/mqi_cases/{context.case_id}"
            remote_csv_path = getattr(context, 'remote_csv_path', f"{remote_case_dir}/csv_data")
            
            job_result = context.remote_handler.submit_simulation_job(
                case_id=context.case_id,
                remote_case_dir=remote_case_dir,
                remote_csv_dir=remote_csv_path,
                gpu_uuid=gpu_allocation.gpu_uuid
            )
            
            if not job_result.success:
                error_msg = f"Failed to submit HPC job: {job_result.error}"
                context.logger.error(error_msg, {"case_id": context.case_id})
                context.gpu_repo.release_gpu(gpu_allocation.gpu_uuid)
                context.case_repo.update_case_status(context.case_id, CaseStatus.FAILED)
                return FailedState()
            
            # Poll for job completion
            job_id = job_result.job_id
            context.logger.info("HPC job submitted, polling for completion", {
                "case_id": context.case_id,
                "job_id": job_id
            })
            
            job_status = context.remote_handler.wait_for_job_completion(
                job_id=job_id,
                timeout_seconds=3600  # 1 hour timeout
            )
            
            # Release GPU after job completion
            context.gpu_repo.release_gpu(gpu_allocation['gpu_uuid'])
            
            if job_status.failed:
                error_msg = f"HPC job failed: {job_status.error}"
                context.logger.error(error_msg, {
                    "case_id": context.case_id,
                    "job_id": job_id
                })
                context.case_repo.update_case_status(context.case_id, CaseStatus.FAILED)
                return FailedState()
            
            context.logger.info("HPC simulation completed successfully", {
                "case_id": context.case_id,
                "job_id": job_id
            })
            
            return DownloadState()
            
        except Exception as e:
            # Make sure to release GPU on any error
            if 'gpu_allocation' in locals() and gpu_allocation:
                context.gpu_repo.release_gpu(gpu_allocation['gpu_uuid'])
                
            error_msg = f"HPC execution error: {str(e)}"
            context.logger.error(error_msg, {
                "case_id": context.case_id,
                "exception_type": type(e).__name__
            })
            context.case_repo.update_case_status(context.case_id, CaseStatus.FAILED)
            return FailedState()

    def get_state_name(self) -> str:
        return "HPC Execution"


class DownloadState(WorkflowState):
    """
    Download state - downloads result files from HPC via SFTP.
    FROM: DownloadState from original states.py.
    """

    def execute(self, context: 'WorkflowManager') -> WorkflowState:
        """
        Download result files from HPC cluster.
        FROM: File download logic from original workflow.
        """
        context.logger.info("Downloading results from HPC cluster", {
            "case_id": context.case_id
        })
        
        try:
            remote_case_dir = f"/tmp/mqi_cases/{context.case_id}"
            
            # Download result files
            result_files = [
                "output.raw",
                "simulation.log",
                "metadata.json"
            ]
            
            for file_name in result_files:
                result = context.remote_handler.download_file(
                    remote_file_path=f"{remote_case_dir}/{file_name}",
                    local_dir=context.case_path
                )
                
                if not result.success:
                    # Log warning but don't fail - some files might be optional
                    context.logger.warning(f"Failed to download {file_name}", {
                        "case_id": context.case_id,
                        "file_name": file_name,
                        "error": result.error
                    })
            
            # Verify that at least the main output file was downloaded
            main_output = context.case_path / "output.raw"
            if not main_output.exists():
                error_msg = "Main output file was not downloaded"
                context.logger.error(error_msg, {
                    "case_id": context.case_id,
                    "expected_file": str(main_output)
                })
                context.case_repo.update_case_status(context.case_id, CaseStatus.FAILED)
                return FailedState()
            
            # Clean up remote directories
            context.remote_handler.cleanup_remote_directory(remote_case_dir)
            
            # Clean up remote CSV directory if it exists in context
            remote_csv_path = getattr(context, 'remote_csv_path', None)
            if remote_csv_path:
                context.logger.info("Cleaning up remote CSV directory", {
                    "case_id": context.case_id,
                    "remote_csv_path": remote_csv_path
                })
                context.remote_handler.cleanup_remote_directory(remote_csv_path)
            
            context.logger.info("Results downloaded successfully and remote cleanup completed", {
                "case_id": context.case_id
            })
            
            return PostprocessingState()
            
        except Exception as e:
            error_msg = f"Download error: {str(e)}"
            context.logger.error(error_msg, {
                "case_id": context.case_id,
                "exception_type": type(e).__name__
            })
            context.case_repo.update_case_status(context.case_id, CaseStatus.FAILED)
            return FailedState()

    def get_state_name(self) -> str:
        return "Download Results"

class PostprocessingState(WorkflowState):
    """
    Postprocessing state - runs RawToDCM locally (P3 process).
    FROM: PostprocessingState from original states.py.
    """

    def execute(self, context: 'WorkflowManager') -> WorkflowState:
        """
        Execute local postprocessing using RawToDCM.
        FROM: Postprocessing logic from original workflow.
        """
        context.logger.info("Running RawToDCM postprocessing", {
            "case_id": context.case_id
        })
        
        # Update status to postprocessing
        context.case_repo.update_case_status(context.case_id, CaseStatus.POSTPROCESSING)
        
        try:
            # Run RawToDCM on the simulation output
            input_file = context.case_path / "output.raw"
            output_dir = context.case_path / "dcm_output"
            
            # Ensure output directory exists
            output_dir.mkdir(exist_ok=True)
            
            result = context.local_handler.run_raw_to_dcm(
                input_file=input_file,
                output_dir=output_dir,
                case_path=context.case_path
            )
            
            if not result.success:
                error_msg = f"RawToDCM failed: {result.error}"
                context.logger.error(error_msg, {
                    "case_id": context.case_id,
                    "command_output": result.output
                })
                context.case_repo.update_case_status(context.case_id, CaseStatus.FAILED)
                return FailedState()
            
            # Verify output files were created
            dcm_files = list(output_dir.glob("*.dcm"))
            if not dcm_files:
                error_msg = "No DCM files generated in postprocessing"
                context.logger.error(error_msg, {
                    "case_id": context.case_id,
                    "output_dir": str(output_dir)
                })
                context.case_repo.update_case_status(context.case_id, CaseStatus.FAILED)
                return FailedState()
                
            context.logger.info("Postprocessing completed successfully", {
                "case_id": context.case_id,
                "output_dir": str(output_dir),
                "dcm_files_count": len(dcm_files)
            })
            
            # Clean up temporary files
            temp_files = [
                "output.raw",
                "simulation.log"
            ]
            
            for temp_file in temp_files:
                temp_path = context.case_path / temp_file
                if temp_path.exists():
                    temp_path.unlink()
            
            # Clean up CSV processing directory
            case_dirs = context.local_handler.settings.get_case_directories()
            processing_dir = str(case_dirs['processing']).format(
                case_id=context.case_id,
                base_directory=context.local_handler.settings.get_base_directory()
            )
            processing_path = Path(processing_dir)
            if processing_path.exists() and processing_path.is_dir():
                # Remove all CSV files in the processing directory
                csv_files = list(processing_path.glob("*.csv"))
                for csv_file in csv_files:
                    csv_file.unlink()
                # Remove the directory if it's empty
                try:
                    processing_path.rmdir()
                except OSError:
                    # Directory not empty, leave it
                    pass
                    
            context.logger.debug("Temporary files and CSV processing directory cleaned up", {
                "case_id": context.case_id,
                "processing_dir": str(processing_path)
            })
            
            return CompletedState()
            
        except Exception as e:
            error_msg = f"Postprocessing error: {str(e)}"
            context.logger.error(error_msg, {
                "case_id": context.case_id,
                "exception_type": type(e).__name__
            })
            context.case_repo.update_case_status(context.case_id, CaseStatus.FAILED)
            return FailedState()

    def get_state_name(self) -> str:
        return "Postprocessing"

class CompletedState(WorkflowState):
    """
    Final completed state.
    FROM: Completion handling from original states.py.
    """

    def execute(self, context: 'WorkflowManager') -> Optional[WorkflowState]:
        """
        Handle completion tasks.
        FROM: Completion logic from original workflow.
        """
        context.logger.info("Workflow completed successfully", {
            "case_id": context.case_id,
            "case_path": str(context.case_path)
        })
        
        # Final status update
        context.case_repo.update_case_status(context.case_id, CaseStatus.COMPLETED)
        
        # Record workflow completion
        context.case_repo.record_workflow_step(
            case_id=context.case_id,
            step=WorkflowStep.COMPLETED,
            status="completed",
            error_message="Workflow successfully completed all states"
        )
        
        return None  # Terminal state

    def get_state_name(self) -> str:
        return "Completed"

class FailedState(WorkflowState):
    """
    Failed state for error handling.
    FROM: Error handling from original states.py.
    """

    def execute(self, context: 'WorkflowManager') -> Optional[WorkflowState]:
        """
        Handle failure cleanup.
        FROM: Error handling logic from original workflow.
        """
        context.logger.error("Workflow entered failed state", {
            "case_id": context.case_id
        })
        
        # Update case status to failed
        context.case_repo.update_case_status(context.case_id, CaseStatus.FAILED)
        
        # Release any allocated GPU resources
        try:
            context.gpu_repo.release_all_for_case(context.case_id)
            context.logger.info("Released GPU resources for failed case", {
                "case_id": context.case_id
            })
        except Exception as e:
            context.logger.warning("Failed to release GPU resources during cleanup", {
                "case_id": context.case_id,
                "error": str(e)
            })
        
        # Record failure in workflow steps
        context.case_repo.record_workflow_step(
            case_id=context.case_id,
            step=WorkflowStep.FAILED,
            status="failed",
            error_message="Workflow terminated due to error"
        )
        
        return None  # Terminal state

    def get_state_name(self) -> str:
        return "Failed"