# =====================================================================================
# Target File: src/domain/states.py
# Source Reference: src/states.py
# =====================================================================================

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.core.workflow_manager import WorkflowManager

from src.domain.enums import CaseStatus
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
    Initial state for new cases - validates case structure and requirements.
    FROM: Initial state logic from original states.py.
    """

    def execute(self, context: 'WorkflowManager') -> WorkflowState:
        """
        Perform initial validation and setup.
        FROM: Initial validation logic from original workflow.
        """
        context.logger.info("Performing initial validation and setup", {
            "case_id": context.case_id,
            "case_path": str(context.case_path)
        })
        
        # Update case status
        context.case_repo.update_case_status(context.case_id, CaseStatus.PREPROCESSING)
        
        # Validate required files and directory structure
        required_files = ["input.mqi", "config.json"]
        for file_name in required_files:
            required_file = context.case_path / file_name
            if not required_file.exists():
                error_msg = f"Required file not found: {required_file}"
                context.logger.error(error_msg, {
                    "case_id": context.case_id,
                    "missing_file": str(required_file)
                })
                context.case_repo.update_case_status(context.case_id, CaseStatus.FAILED)
                return FailedState()
        
        # Validate case directory structure
        if not context.case_path.is_dir():
            error_msg = f"Case path is not a valid directory: {context.case_path}"
            context.logger.error(error_msg, {"case_id": context.case_id})
            context.case_repo.update_case_status(context.case_id, CaseStatus.FAILED)
            return FailedState()
            
        context.logger.info("Initial validation completed successfully", {
            "case_id": context.case_id
        })
        
        return PreprocessingState()

    def get_state_name(self) -> str:
        return "Initial Validation"

class PreprocessingState(WorkflowState):
    """
    Preprocessing state - runs mqi_interpreter locally (P2 process).
    FROM: Preprocessing state from original states.py.
    """

    def execute(self, context: 'WorkflowManager') -> WorkflowState:
        """
        Execute local preprocessing using mqi_interpreter.
        FROM: Preprocessing logic from original workflow.
        """
        context.logger.info("Running mqi_interpreter preprocessing", {
            "case_id": context.case_id
        })
        
        try:
            # Run mqi_interpreter on the case
            input_file = context.case_path / "input.mqi"
            output_file = context.case_path / "preprocessed.json"
            
            result = context.local_handler.run_mqi_interpreter(
                input_file=input_file,
                output_file=output_file,
                case_path=context.case_path
            )
            
            if not result.success:
                error_msg = f"mqi_interpreter failed: {result.error}"
                context.logger.error(error_msg, {
                    "case_id": context.case_id,
                    "command_output": result.output
                })
                context.case_repo.update_case_status(context.case_id, CaseStatus.FAILED)
                return FailedState()
            
            # Verify output file was created
            if not output_file.exists():
                error_msg = "Preprocessing output file not created"
                context.logger.error(error_msg, {
                    "case_id": context.case_id,
                    "expected_output": str(output_file)
                })
                context.case_repo.update_case_status(context.case_id, CaseStatus.FAILED)
                return FailedState()
                
            context.logger.info("Preprocessing completed successfully", {
                "case_id": context.case_id,
                "output_file": str(output_file)
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
    File upload state - uploads files to HPC via SFTP.
    FROM: FileUploadState from original states.py.
    """

    def execute(self, context: 'WorkflowManager') -> WorkflowState:
        """
        Upload case files to HPC cluster via SFTP.
        FROM: File upload logic from original workflow.
        """
        context.logger.info("Uploading files to HPC cluster", {
            "case_id": context.case_id
        })
        
        try:
            # Upload required files to HPC
            files_to_upload = [
                "preprocessed.json",
                "config.json",
                "input.mqi"
            ]
            
            remote_case_dir = f"/tmp/mqi_cases/{context.case_id}"
            
            for file_name in files_to_upload:
                local_file = context.case_path / file_name
                if local_file.exists():
                    result = context.remote_handler.upload_file(
                        local_file=local_file,
                        remote_dir=remote_case_dir
                    )
                    if not result.success:
                        error_msg = f"Failed to upload {file_name}: {result.error}"
                        context.logger.error(error_msg, {
                            "case_id": context.case_id,
                            "file_name": file_name
                        })
                        context.case_repo.update_case_status(context.case_id, CaseStatus.FAILED)
                        return FailedState()
            
            context.logger.info("File upload completed successfully", {
                "case_id": context.case_id,
                "remote_dir": remote_case_dir
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
            
            # Submit simulation job to HPC
            remote_case_dir = f"/tmp/mqi_cases/{context.case_id}"
            job_result = context.remote_handler.submit_simulation_job(
                case_id=context.case_id,
                remote_case_dir=remote_case_dir,
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
            context.gpu_repo.release_gpu(gpu_allocation.gpu_uuid)
            
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
                context.gpu_repo.release_gpu(gpu_allocation.gpu_uuid)
                
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
            
            # Clean up remote directory
            context.remote_handler.cleanup_remote_directory(remote_case_dir)
            
            context.logger.info("Results downloaded successfully", {
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
                "preprocessed.json",
                "output.raw",
                "simulation.log"
            ]
            
            for temp_file in temp_files:
                temp_path = context.case_path / temp_file
                if temp_path.exists():
                    temp_path.unlink()
                    
            context.logger.debug("Temporary files cleaned up", {
                "case_id": context.case_id
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
            step_name="workflow_completed",
            status="completed",
            details="Workflow successfully completed all states"
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
            step_name="workflow_failed",
            status="failed",
            details="Workflow terminated due to error"
        )
        
        return None  # Terminal state

    def get_state_name(self) -> str:
        return "Failed"