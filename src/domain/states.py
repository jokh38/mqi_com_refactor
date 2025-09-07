# =====================================================================================
# Target File: src/domain/states.py
# Source Reference: src/states.py
# =====================================================================================

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.core.workflow_manager import WorkflowManager

from src.core.case_aggregator import update_case_status_from_beams
from src.domain.enums import BeamStatus, CaseStatus, WorkflowStep
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
    Initial state for a new beam - validates beam structure and generates moqui_tps.in.
    """

    def execute(self, context: 'WorkflowManager') -> WorkflowState:
        """
        Perform initial validation for the beam and generate its moqui_tps.in file.
        """
        context.logger.info("Performing initial validation and moqui_tps.in generation for beam", {
            "beam_id": context.id,
            "beam_path": str(context.path)
        })
        
        # Update beam status
        context.case_repo.update_beam_status(context.id, BeamStatus.PREPROCESSING)
        
        # Validate beam directory structure
        if not context.path.is_dir():
            error_msg = f"Beam path is not a valid directory: {context.path}"
            context.logger.error(error_msg, {"beam_id": context.id})
            context.case_repo.update_beam_status(context.id, BeamStatus.FAILED, error_message=error_msg)
            return FailedState()
        
        # Generate moqui_tps.in configuration file for the beam
        try:
            context.logger.info("Generating moqui_tps.in configuration file", {
                "beam_id": context.id
            })
            
            # Get GPU allocation for the beam to determine GPU ID
            # Note: GPU is locked per beam job now
            gpu_allocation = context.gpu_repo.find_and_lock_available_gpu(context.id)
            if not gpu_allocation:
                error_msg = "No GPU available for TPS generation"
                context.logger.error(error_msg, {"beam_id": context.id})
                context.case_repo.update_beam_status(context.id, BeamStatus.FAILED, error_message=error_msg)
                return FailedState()
            
            gpu_id = 0  # Default to 0, could be enhanced to parse from allocation
            
            # Generate the TPS file inside the beam directory
            success = context.tps_generator.generate_tps_file(
                case_path=context.path, # This is now the beam path
                case_id=context.id,   # This is now the beam id
                gpu_id=gpu_id,
                execution_mode="remote"
            )
            
            context.gpu_repo.release_gpu(gpu_allocation['gpu_uuid'])
            
            if not success:
                error_msg = "Failed to generate moqui_tps.in file"
                context.logger.error(error_msg, {"beam_id": context.id})
                context.case_repo.update_beam_status(context.id, BeamStatus.FAILED, error_message=error_msg)
                return FailedState()
            
            tps_file = context.path / "moqui_tps.in"
            if not tps_file.exists():
                error_msg = "Generated moqui_tps.in file not found"
                context.logger.error(error_msg, {
                    "beam_id": context.id,
                    "expected_file": str(tps_file)
                })
                context.case_repo.update_beam_status(context.id, BeamStatus.FAILED, error_message=error_msg)
                return FailedState()
            
            # Record workflow step for the parent case
            beam = context.case_repo.get_beam(context.id)
            if beam:
                context.case_repo.record_workflow_step(
                    case_id=beam.parent_case_id,
                    step=WorkflowStep.TPS_GENERATION,
                    status="completed",
                    metadata={"beam_id": context.id, "message": "TPS configuration file generated successfully"}
                )
            
            context.logger.info("Initial validation and TPS generation completed successfully for beam", {
                "beam_id": context.id,
                "tps_file": str(tps_file)
            })
            
            return PreprocessingState()
            
        except Exception as e:
            if 'gpu_allocation' in locals() and gpu_allocation:
                context.gpu_repo.release_gpu(gpu_allocation['gpu_uuid'])
                
            error_msg = f"Initial state error for beam: {str(e)}"
            context.logger.error(error_msg, {
                "beam_id": context.id,
                "exception_type": type(e).__name__
            })
            context.case_repo.update_beam_status(context.id, BeamStatus.FAILED, error_message=error_msg)
            return FailedState()

    def get_state_name(self) -> str:
        return "Initial Validation"


class PreprocessingState(WorkflowState):
    """
    Preprocessing state - runs mqi_interpreter locally for a single beam.
    """

    def execute(self, context: 'WorkflowManager') -> WorkflowState:
        """
        Execute local preprocessing using mqi_interpreter for the given beam.
        """
        context.logger.info("Running mqi_interpreter preprocessing for beam", {
            "beam_id": context.id
        })
        
        try:
            # The mqi_interpreter process reads from and writes to the beam directory.
            beam_path = context.path
            
            # The input file 'moqui_tps.in' is expected to be in the beam directory.
            input_file = beam_path / "moqui_tps.in"
            if not input_file.exists():
                error_msg = f"moqui_tps.in file not found in beam directory: {input_file}"
                context.logger.error(error_msg, {"beam_id": context.id})
                context.case_repo.update_beam_status(context.id, BeamStatus.FAILED, error_message=error_msg)
                return FailedState()

            # Execute mqi_interpreter. Output CSVs are generated in the beam_path.
            result = context.local_handler.run_mqi_interpreter(
                beam_directory=beam_path,
                output_dir=beam_path  # Output CSVs to the beam's own directory
            )
            
            if not result.success:
                error_msg = f"mqi_interpreter failed for beam '{context.id}'. Error: {result.error}"
                context.logger.error(error_msg, {
                    "beam_id": context.id,
                    "command_output": result.output,
                    "stderr": result.error
                })
                context.case_repo.update_beam_status(context.id, BeamStatus.FAILED, error_message=error_msg)
                return FailedState()

            # Verify that CSV files were generated in the beam directory
            csv_files = list(beam_path.glob("*.csv"))
            if not csv_files:
                error_msg = "No CSV files generated after preprocessing beam"
                context.logger.error(error_msg, {
                    "beam_id": context.id,
                    "beam_path": str(beam_path)
                })
                context.case_repo.update_beam_status(context.id, BeamStatus.FAILED, error_message=error_msg)
                return FailedState()
                
            context.logger.info("Preprocessing completed successfully for beam", {
                "beam_id": context.id,
                "beam_path": str(beam_path),
                "csv_files_count": len(csv_files)
            })
            
            return FileUploadState()
            
        except Exception as e:
            error_msg = f"Preprocessing error for beam: {str(e)}"
            context.logger.error(error_msg, {
                "beam_id": context.id,
                "exception_type": type(e).__name__
            })
            context.case_repo.update_beam_status(context.id, BeamStatus.FAILED, error_message=error_msg)
            return FailedState()

    def get_state_name(self) -> str:
        return "Preprocessing"

class FileUploadState(WorkflowState):
    """
    File upload state - uploads beam-specific files to a dedicated directory on the HPC.
    """

    def execute(self, context: 'WorkflowManager') -> WorkflowState:
        """
        Uploads moqui_tps.in and all *.csv files from the local beam directory to the HPC.
        """
        context.logger.info("Uploading beam files to HPC", {"beam_id": context.id})
        context.case_repo.update_beam_status(context.id, BeamStatus.UPLOADING)

        try:
            beam = context.case_repo.get_beam(context.id)
            if not beam:
                error_msg = f"Could not retrieve beam data for beam_id: {context.id}"
                context.logger.error(error_msg, {"beam_id": context.id})
                # No need to update status again, just fail
                return FailedState()

            # Construct the remote path: /remote/path/{case_id}/{beam_id}/
            hpc_paths = context.local_handler.settings.get_hpc_paths()
            remote_base_dir = hpc_paths.get("remote_case_path_template") # e.g., /mnt/hpc/cases
            if not remote_base_dir:
                raise ProcessingError("`remote_case_path_template` not configured in settings.")

            remote_beam_dir = f"{remote_base_dir}/{beam.parent_case_id}/{context.id}"
            context.shared_context["remote_beam_dir"] = remote_beam_dir

            # Find all files to upload from the local beam directory
            local_beam_path = context.path
            files_to_upload = list(local_beam_path.glob("*.csv"))
            tps_file = local_beam_path / "moqui_tps.in"
            
            if not tps_file.exists():
                error_msg = f"moqui_tps.in not found in local beam directory: {local_beam_path}"
                context.logger.error(error_msg, {"beam_id": context.id})
                context.case_repo.update_beam_status(context.id, BeamStatus.FAILED, error_message=error_msg)
                return FailedState()
            
            files_to_upload.append(tps_file)

            if not files_to_upload:
                error_msg = "No files found in local beam directory to upload."
                context.logger.warning(error_msg, {"beam_id": context.id})
                # This might not be a failure, could be a beam with no data.
                # For now, we proceed, but this could be a failure point.
                return HpcExecutionState()

            # Upload all files
            for file_path in files_to_upload:
                result = context.remote_handler.upload_file(
                    local_file=file_path, remote_dir=remote_beam_dir
                )
                if not result.success:
                    error_msg = f"Failed to upload file {file_path.name}: {result.error}"
                    context.logger.error(error_msg, {"beam_id": context.id})
                    context.case_repo.update_beam_status(context.id, BeamStatus.FAILED, error_message=error_msg)
                    return FailedState()

            context.logger.info(f"Successfully uploaded {len(files_to_upload)} files for beam", {
                "beam_id": context.id,
                "remote_beam_dir": remote_beam_dir
            })

            return HpcExecutionState()

        except Exception as e:
            error_msg = f"File upload error for beam: {str(e)}"
            context.logger.error(error_msg, {
                "beam_id": context.id,
                "exception_type": type(e).__name__
            })
            context.case_repo.update_beam_status(context.id, BeamStatus.FAILED, error_message=error_msg)
            return FailedState()

    def get_state_name(self) -> str:
        return "File Upload"


class HpcExecutionState(WorkflowState):
    """
    HPC execution state - runs MOQUI simulation on HPC for a single beam.
    """

    def execute(self, context: 'WorkflowManager') -> WorkflowState:
        """
        Submits a MOQUI simulation job for the beam and polls for completion.
        """
        context.logger.info("Starting HPC simulation for beam", {"beam_id": context.id})
        
        try:
            # Allocate GPU for the job
            gpu_allocation = context.gpu_repo.find_and_lock_available_gpu(context.id)
            if not gpu_allocation:
                error_msg = "No GPU available for simulation"
                context.logger.error(error_msg, {"beam_id": context.id})
                context.case_repo.update_beam_status(context.id, BeamStatus.FAILED, error_message=error_msg)
                return FailedState()
            
            context.logger.info("GPU allocated for simulation", {
                "beam_id": context.id,
                "gpu_uuid": gpu_allocation.get('gpu_uuid')
            })
            
            remote_beam_dir = context.shared_context.get("remote_beam_dir")
            if not remote_beam_dir:
                raise ProcessingError("Remote beam directory not found in shared context.")

            # Submit simulation job to HPC for the specific beam
            job_result = context.remote_handler.submit_simulation_job(
                beam_id=context.id,
                remote_beam_dir=remote_beam_dir,
                gpu_uuid=gpu_allocation.get('gpu_uuid')
            )
            
            if not job_result.success:
                error_msg = f"Failed to submit HPC job: {job_result.error}"
                context.logger.error(error_msg, {"beam_id": context.id})
                context.gpu_repo.release_gpu(gpu_allocation.get('gpu_uuid'))
                context.case_repo.update_beam_status(context.id, BeamStatus.FAILED, error_message=error_msg)
                return FailedState()
            
            job_id = job_result.job_id
            context.case_repo.assign_hpc_job_id_to_beam(context.id, job_id)
            context.case_repo.update_beam_status(context.id, BeamStatus.HPC_QUEUED)

            context.logger.info("HPC job submitted, polling for completion", {
                "beam_id": context.id,
                "job_id": job_id
            })
            
            # This is a long-running wait. We can update status to RUNNING once polling starts.
            context.case_repo.update_beam_status(context.id, BeamStatus.HPC_RUNNING)
            job_status = context.remote_handler.wait_for_job_completion(
                job_id=job_id,
                timeout_seconds=3600  # 1 hour timeout
            )
            
            context.gpu_repo.release_gpu(gpu_allocation.get('gpu_uuid'))
            
            if job_status.failed:
                error_msg = f"HPC job failed: {job_status.error_message}"
                context.logger.error(error_msg, {"beam_id": context.id, "job_id": job_id})
                context.case_repo.update_beam_status(context.id, BeamStatus.FAILED, error_message=error_msg)
                return FailedState()
            
            context.logger.info("HPC simulation completed successfully for beam", {
                "beam_id": context.id,
                "job_id": job_id
            })
            
            return DownloadState()
            
        except Exception as e:
            if 'gpu_allocation' in locals() and gpu_allocation:
                context.gpu_repo.release_gpu(gpu_allocation.get('gpu_uuid'))
                
            error_msg = f"HPC execution error for beam: {str(e)}"
            context.logger.error(error_msg, {
                "beam_id": context.id,
                "exception_type": type(e).__name__
            })
            context.case_repo.update_beam_status(context.id, BeamStatus.FAILED, error_message=error_msg)
            return FailedState()

    def get_state_name(self) -> str:
        return "HPC Execution"


class DownloadState(WorkflowState):
    """
    Download state - downloads the raw result file from the HPC for a single beam.
    """

    def execute(self, context: 'WorkflowManager') -> WorkflowState:
        """
        Downloads the 'output.raw' file from the remote beam directory to a local results directory.
        """
        context.logger.info("Downloading results from HPC for beam", {"beam_id": context.id})
        context.case_repo.update_beam_status(context.id, BeamStatus.DOWNLOADING)

        try:
            beam = context.case_repo.get_beam(context.id)
            if not beam:
                raise ProcessingError(f"Could not retrieve beam data for beam_id: {context.id}")

            remote_beam_dir = context.shared_context.get("remote_beam_dir")
            if not remote_beam_dir:
                raise ProcessingError("Remote beam directory not found in shared context.")

            # Define local download path based on config
            case_dirs = context.local_handler.settings.get_case_directories()
            # Using final_dicom_directory as the base for results, as per interpretation of refactor doc
            local_result_dir_template = case_dirs.get("final_dicom")
            if not local_result_dir_template:
                 raise ProcessingError("`final_dicom_directory` not configured in settings.")
            
            local_result_dir = Path(str(local_result_dir_template).format(case_id=beam.parent_case_id))
            local_beam_result_dir = local_result_dir / beam.beam_id
            local_beam_result_dir.mkdir(parents=True, exist_ok=True)
            
            # Download the main output file
            remote_file_path = f"{remote_beam_dir}/output.raw"
            result = context.remote_handler.download_file(
                remote_file_path=remote_file_path,
                local_dir=local_beam_result_dir
            )

            if not result.success:
                error_msg = f"Failed to download output.raw: {result.error}"
                context.logger.error(error_msg, {"beam_id": context.id})
                context.case_repo.update_beam_status(context.id, BeamStatus.FAILED, error_message=error_msg)
                return FailedState()

            main_output_file = local_beam_result_dir / "output.raw"
            if not main_output_file.exists():
                error_msg = "Main output file 'output.raw' was not downloaded."
                context.logger.error(error_msg, {"beam_id": context.id})
                context.case_repo.update_beam_status(context.id, BeamStatus.FAILED, error_message=error_msg)
                return FailedState()
            
            # Store the path for postprocessing
            context.shared_context["raw_output_file"] = main_output_file

            # Clean up remote directory
            context.remote_handler.cleanup_remote_directory(remote_beam_dir)
            
            context.logger.info("Beam result downloaded successfully", {"beam_id": context.id})
            return PostprocessingState()

        except Exception as e:
            error_msg = f"Download error for beam: {str(e)}"
            context.logger.error(error_msg, {
                "beam_id": context.id,
                "exception_type": type(e).__name__
            })
            context.case_repo.update_beam_status(context.id, BeamStatus.FAILED, error_message=error_msg)
            return FailedState()

    def get_state_name(self) -> str:
        return "Download Results"

class PostprocessingState(WorkflowState):
    """
    Postprocessing state - runs RawToDCM locally for a single beam's output.
    """

    def execute(self, context: 'WorkflowManager') -> WorkflowState:
        """
        Execute local postprocessing using RawToDCM on the downloaded raw file.
        """
        context.logger.info("Running RawToDCM postprocessing for beam", {"beam_id": context.id})
        context.case_repo.update_beam_status(context.id, BeamStatus.POSTPROCESSING)

        try:
            input_file = context.shared_context.get("raw_output_file")
            if not input_file or not input_file.exists():
                raise ProcessingError(f"Raw output file not found in shared context or does not exist: {input_file}")

            # Output DICOMs to a 'dcm_output' subdirectory in the beam's result folder
            output_dir = input_file.parent / "dcm_output"
            output_dir.mkdir(exist_ok=True)

            result = context.local_handler.run_raw_to_dcm(
                input_file=input_file,
                output_dir=output_dir,
                case_path=context.path # The original beam source path might be needed for context
            )
            
            if not result.success:
                error_msg = f"RawToDCM failed for beam {context.id}: {result.error}"
                context.logger.error(error_msg, {
                    "beam_id": context.id,
                    "command_output": result.output
                })
                context.case_repo.update_beam_status(context.id, BeamStatus.FAILED, error_message=error_msg)
                return FailedState()
            
            dcm_files = list(output_dir.glob("*.dcm"))
            if not dcm_files:
                error_msg = "No DCM files generated in postprocessing for beam."
                context.logger.error(error_msg, {"beam_id": context.id})
                context.case_repo.update_beam_status(context.id, BeamStatus.FAILED, error_message=error_msg)
                return FailedState()
                
            context.logger.info("Postprocessing completed successfully for beam", {
                "beam_id": context.id,
                "output_dir": str(output_dir),
                "dcm_files_count": len(dcm_files)
            })
            
            # Clean up the raw file
            input_file.unlink()
            
            return CompletedState()
            
        except Exception as e:
            error_msg = f"Postprocessing error for beam: {str(e)}"
            context.logger.error(error_msg, {
                "beam_id": context.id,
                "exception_type": type(e).__name__
            })
            context.case_repo.update_beam_status(context.id, BeamStatus.FAILED, error_message=error_msg)
            return FailedState()

    def get_state_name(self) -> str:
        return "Postprocessing"

class CompletedState(WorkflowState):
    """
    Final completed state for a beam.
    """

    def execute(self, context: 'WorkflowManager') -> Optional[WorkflowState]:
        """
        Handles completion tasks for the beam.
        """
        context.logger.info("Beam workflow completed successfully", {
            "beam_id": context.id,
            "beam_path": str(context.path)
        })
        
        # Final status update for the beam
        context.case_repo.update_beam_status(context.id, BeamStatus.COMPLETED)
        
        # Record workflow completion for the parent case
        beam = context.case_repo.get_beam(context.id)
        if beam:
            context.case_repo.record_workflow_step(
                case_id=beam.parent_case_id,
                step=WorkflowStep.COMPLETED,
                status="completed",
                metadata={"beam_id": context.id, "message": "Beam workflow successfully completed."}
            )
            # After beam is done, check if the parent case is now complete
            update_case_status_from_beams(beam.parent_case_id, context.case_repo)

        return None  # Terminal state

    def get_state_name(self) -> str:
        return "Completed"

class FailedState(WorkflowState):
    """
    Failed state for beam error handling.
    """

    def execute(self, context: 'WorkflowManager') -> Optional[WorkflowState]:
        """
        Handles failure cleanup for the beam.
        """
        context.logger.error("Beam workflow entered failed state", {
            "beam_id": context.id
        })
        
        # The status is likely already FAILED, but we ensure it here.
        context.case_repo.update_beam_status(context.id, BeamStatus.FAILED)
        
        # Release any allocated GPU resources for this specific beam
        try:
            # The 'assigned_case' in gpu_resources now holds the beam_id
            context.gpu_repo.release_all_for_case(context.id)
            context.logger.info("Released GPU resources for failed beam", {
                "beam_id": context.id
            })
        except Exception as e:
            context.logger.warning("Failed to release GPU resources during cleanup for beam", {
                "beam_id": context.id,
                "error": str(e)
            })
        
        # Record failure in workflow steps for the parent case
        beam = context.case_repo.get_beam(context.id)
        if beam:
            context.case_repo.record_workflow_step(
                case_id=beam.parent_case_id,
                step=WorkflowStep.FAILED,
                status="failed",
                metadata={"beam_id": context.id, "message": "Beam workflow terminated due to error."}
            )
            # After beam has failed, check if the parent case should be marked as failed
            update_case_status_from_beams(beam.parent_case_id, context.case_repo)
        
        return None  # Terminal state

    def get_state_name(self) -> str:
        return "Failed"