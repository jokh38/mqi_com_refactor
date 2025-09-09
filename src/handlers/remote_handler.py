# =====================================================================================
# Target File: src/handlers/remote_handler.py
# Source Reference: src/remote_handler.py
# =====================================================================================
"""!
@file remote_handler.py
@brief Manages HPC communication, remote execution, and file transfers.
"""

import os
import time
from typing import Optional, Dict, Any, NamedTuple
from pathlib import Path
import paramiko
from paramiko import SSHClient, SFTPClient

from src.infrastructure.logging_handler import StructuredLogger
from src.config.settings import Settings
from src.utils.retry_policy import RetryPolicy
from src.domain.errors import ProcessingError
from src.handlers.local_handler import ExecutionResult


class UploadResult(NamedTuple):
    """!
    @brief Result from a file upload operation.
    """

    success: bool
    error: Optional[str] = None


class JobSubmissionResult(NamedTuple):
    """!
    @brief Result from an HPC job submission.
    """

    success: bool
    job_id: Optional[str] = None
    error: Optional[str] = None


class JobStatus(NamedTuple):
    """!
    @brief Status of an HPC job.
    """

    job_id: str
    status: str
    failed: bool
    completed: bool
    error_message: Optional[str] = None


class DownloadResult(NamedTuple):
    """!
    @brief Result from a file download operation.
    """

    success: bool
    error: Optional[str] = None


class RemoteHandler:
    """!
    @brief Manages HPC communication (SSH/SFTP), remote execution and file transfers.
    @details This class uses injected dependencies for retry policy and settings,
             and provides improved error handling and connection management.
    """

    def __init__(
        self, settings: Settings, logger: StructuredLogger, retry_policy: RetryPolicy
    ):
        """!
        @brief Initialize RemoteHandler with injected dependencies.
        @param settings: Application settings containing HPC configuration.
        @param logger: Logger for recording operations.
        @param retry_policy: Retry policy for failed operations.
        """
        self.settings = settings
        self.logger = logger
        self.retry_policy = retry_policy

        # Connection instances
        self._ssh_client: Optional[SSHClient] = None
        self._sftp_client: Optional[SFTPClient] = None

        # Connection state
        self._connected = False

    def connect(self) -> None:
        """!
        @brief Establish SSH/SFTP connections to the remote HPC system.
        @raises ProcessingError: If HPC connection settings are not configured or connection fails.
        """
        self.logger.info(
            "Establishing HPC connection",
            {
                "host": (
                    self.settings.hpc.hostname
                    if hasattr(self.settings, "hpc")
                    else "configured"
                )
            },
        )

        try:
            hpc_config = self.settings.get_hpc_connection()
            if not hpc_config:
                raise ProcessingError("HPC connection settings not configured.")

            # Create SSH client
            self._ssh_client = paramiko.SSHClient()
            self._ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            # Connect to HPC system
            self._ssh_client.connect(
                hostname=hpc_config.get("host"),
                username=hpc_config.get("user"),
                key_filename=hpc_config.get("ssh_key_path"),
                timeout=hpc_config.get("connection_timeout_seconds", 30),
            )

            # Create SFTP client
            self._sftp_client = self._ssh_client.open_sftp()

            self._connected = True
            self.logger.info("HPC connection established successfully")

        except Exception as e:
            self.logger.error("Failed to establish HPC connection", {"error": str(e)})
            self._cleanup_connections()
            raise ProcessingError(f"Failed to connect to HPC system: {e}")

    def disconnect(self) -> None:
        """!
        @brief Close SSH/SFTP connections.
        """
        self.logger.debug("Closing HPC connections")
        self._cleanup_connections()

    def _cleanup_connections(self) -> None:
        """!
        @brief Clean up connection resources.
        """
        if self._sftp_client:
            try:
                self._sftp_client.close()
            except Exception as e:
                self.logger.warning("Error closing SFTP connection", {"error": str(e)})
            self._sftp_client = None

        if self._ssh_client:
            try:
                self._ssh_client.close()
            except Exception as e:
                self.logger.warning("Error closing SSH connection", {"error": str(e)})
            self._ssh_client = None

        self._connected = False

    def _ensure_connected(self) -> None:
        """!
        @brief Ensure a connection is established before performing operations.
        """
        if not self._connected or not self._ssh_client:
            self.connect()

    def execute_remote_command(
        self, context_id: str, command: str, remote_cwd: Optional[str] = None
    ) -> ExecutionResult:
        """!
        @brief Execute a command on the remote HPC system.
        @param context_id: An identifier for the operation for logging purposes (e.g., beam_id, 'gpu_monitoring').
        @param command: The command to execute.
        @param remote_cwd: The remote working directory (optional).
        @return An ExecutionResult containing the outcome of the execution.
        """
        self.logger.info(
            "Executing remote command",
            {"context_id": context_id, "command": command, "remote_cwd": remote_cwd},
        )

        def execute_attempt():
            self._ensure_connected()

            if not self._ssh_client:
                raise ProcessingError("SSH client not available")

            # Build full command with working directory if specified
            full_command = command
            if remote_cwd:
                full_command = f"cd {remote_cwd} && {command}"

            # Execute command
            stdin, stdout, stderr = self._ssh_client.exec_command(full_command)

            # Get results
            exit_code = stdout.channel.recv_exit_status()
            output = stdout.read().decode("utf-8")
            error = stderr.read().decode("utf-8")

            return ExecutionResult(
                success=(exit_code == 0),
                output=output,
                error=error,
                return_code=exit_code,
            )

        try:
            result = self.retry_policy.execute(
                execute_attempt,
                operation_name="remote_command",
                context={"context_id": context_id, "command": command},
            )

            if result.success:
                self.logger.info(
                    "Remote command completed successfully",
                    {
                        "context_id": context_id,
                        "command": command,
                        "output_length": len(result.output),
                    },
                )
            else:
                self.logger.error(
                    "Remote command failed",
                    {
                        "context_id": context_id,
                        "command": command,
                        "return_code": result.return_code,
                        "error": result.error,
                    },
                )

            return result

        except Exception as e:
            self.logger.error(
                "Remote command execution failed after retries",
                {"context_id": context_id, "command": command, "error": str(e)},
            )

            return ExecutionResult(
                success=False, output="", error=str(e), return_code=-1
            )

    def check_job_status(self, job_id: str) -> Dict[str, Any]:
        """!
        @brief Check the status of a submitted job on the HPC system.
        @param job_id: The HPC job identifier.
        @return A dictionary containing job status information.
        """
        self.logger.debug(
            "Checking HPC job status", {"job_id": job_id}
        )

        status_command = f"squeue -j {job_id} --noheader -o %T"

        try:
            result = self.execute_remote_command("job_status_check", status_command)

            status = "UNKNOWN"
            error_message = None

            if result.success and result.output.strip():
                status = result.output.strip().upper()
            elif not result.success:
                error_message = result.error

            return {
                "job_id": job_id,
                "status": status,
                "queue_time": None,  # Placeholder, not easily available from squeue
                "start_time": None,  # Placeholder
                "completion_time": None,  # Placeholder
                "error_message": error_message,
            }

        except Exception as e:
            self.logger.error(
                "Failed to check job status", {"job_id": job_id, "error": str(e)}
            )
            return {
                "job_id": job_id,
                "status": "UNKNOWN",
                "error_message": str(e),
            }

    def upload_file(self, local_file: Path, remote_dir: str) -> UploadResult:
        """!
        @brief Upload a single file to the HPC system.
        @param local_file: Path to the local file to upload.
        @param remote_dir: The remote directory to upload to.
        @return An UploadResult indicating success or failure.
        """
        self.logger.debug(
            "Uploading file to HPC",
            {"local_file": str(local_file), "remote_dir": remote_dir},
        )

        try:
            self._ensure_connected()

            if not self._sftp_client:
                return UploadResult(
                    success=False, error="SFTP client not available"
                )

            if not local_file.exists():
                return UploadResult(
                    success=False,
                    error=f"Local file does not exist: {local_file}",
                )

            # Create remote directory if it doesn't exist
            self._mkdir_p(self._sftp_client, remote_dir)

            # Upload the file
            remote_file_path = f"{remote_dir}/{local_file.name}".replace("\\", "/")
            self._sftp_client.put(str(local_file), remote_file_path)

            self.logger.debug(
                "File uploaded successfully",
                {"local_file": str(local_file), "remote_file": remote_file_path},
            )

            return UploadResult(success=True)

        except Exception as e:
            error_msg = f"Failed to upload file: {e}"
            self.logger.error(
                error_msg, {"local_file": str(local_file), "remote_dir": remote_dir}
            )
            return UploadResult(success=False, error=error_msg)

    def submit_simulation_job(
        self, beam_id: str, remote_beam_dir: str, gpu_uuid: str
    ) -> JobSubmissionResult:
        """!
        @brief Submit a MOQUI simulation job to the HPC system for a single beam.
        @param beam_id: The beam identifier.
        @param remote_beam_dir: The remote directory for job execution, containing all necessary files.
        @param gpu_uuid: The GPU UUID to use for the simulation.
        @return A JobSubmissionResult with the job ID if successful.
        """
        self.logger.info(
            "Submitting HPC simulation job for beam",
            {
                "beam_id": beam_id,
                "remote_beam_dir": remote_beam_dir,
                "gpu_uuid": gpu_uuid,
            },
        )

        try:
            # The input directory for the simulator is the beam directory itself
            job_script = f"""#!/bin/bash
#SBATCH --job-name=moqui_{beam_id}
#SBATCH --output={remote_beam_dir}/simulation.log
#SBATCH --error={remote_beam_dir}/simulation.err
#SBATCH --gres=gpu:1
#SBATCH --time=01:00:00

cd {remote_beam_dir}
export CUDA_VISIBLE_DEVICES={gpu_uuid}
/usr/local/bin/moqui_simulator --input . --output output.raw
"""

            # Write job script to remote system
            job_script_path = f"{remote_beam_dir}/submit_job.sh"

            self._ensure_connected()
            if not self._sftp_client:
                return JobSubmissionResult(
                    success=False, error="SFTP client not available"
                )

            # Upload job script
            with self._sftp_client.open(job_script_path, "w") as f:
                f.write(job_script)

            # Submit the job
            submit_command = f"sbatch {job_script_path}"
            result = self.execute_remote_command(beam_id, submit_command)

            if not result.success:
                return JobSubmissionResult(
                    success=False,
                    error=f"Job submission failed: {result.error}",
                )

            # Extract job ID from sbatch output
            # Typical sbatch output: "Submitted batch job 12345"
            output_lines = result.output.strip().split("\n")
            job_id = None
            for line in output_lines:
                if "Submitted batch job" in line:
                    job_id = line.split()[-1]
                    break

            if not job_id:
                return JobSubmissionResult(
                    success=False,
                    error="Could not extract job ID from sbatch output",
                )

            self.logger.info(
                "HPC job submitted successfully for beam", {"beam_id": beam_id, "job_id": job_id}
            )

            return JobSubmissionResult(success=True, job_id=job_id)

        except Exception as e:
            error_msg = f"Job submission error: {e}"
            self.logger.error(error_msg, {"beam_id": beam_id})
            return JobSubmissionResult(success=False, error=error_msg)

    def wait_for_job_completion(
        self, job_id: str, timeout_seconds: int = 3600
    ) -> JobStatus:
        """!
        @brief Wait for an HPC job to complete, polling at regular intervals.
        @param job_id: The HPC job identifier.
        @param timeout_seconds: The maximum time to wait for completion.
        @return A JobStatus indicating the final job status.
        """
        self.logger.info(
            "Waiting for HPC job completion",
            {"job_id": job_id, "timeout_seconds": timeout_seconds},
        )

        start_time = time.time()
        poll_interval = 30  # Poll every 30 seconds

        while time.time() - start_time < timeout_seconds:
            try:
                # Check job status using squeue
                status_command = f"squeue -j {job_id} --noheader --format='%T'"
                result = self.execute_remote_command("job_polling", status_command)

                if result.success and result.output.strip():
                    status = result.output.strip().upper()

                    if status in ["COMPLETED", "COMPLETING"]:
                        self.logger.info(
                            "HPC job completed successfully", {"job_id": job_id}
                        )
                        return JobStatus(
                            job_id=job_id, status=status, failed=False, completed=True
                        )
                    elif status in ["FAILED", "CANCELLED", "TIMEOUT", "NODE_FAIL"]:
                        self.logger.error(
                            "HPC job failed", {"job_id": job_id, "status": status}
                        )
                        return JobStatus(
                            job_id=job_id,
                            status=status,
                            failed=True,
                            completed=True,
                            error_message=f"Job failed with status: {status}",
                        )
                    else:
                        # Job is still running (PENDING, RUNNING, etc.)
                        self.logger.debug(
                            "HPC job still running",
                            {"job_id": job_id, "status": status},
                        )
                else:
                    # Job not found in queue - might be completed or failed
                    # Check if job completed by looking at job history
                    history_command = (
                        f"sacct -j {job_id} --noheader --format='State' | head -1"
                    )
                    history_result = self.execute_remote_command(
                        "job_history", history_command
                    )

                    if history_result.success and history_result.output.strip():
                        status = history_result.output.strip().upper()
                        if "COMPLETED" in status:
                            return JobStatus(
                                job_id=job_id,
                                status=status,
                                failed=False,
                                completed=True,
                            )
                        else:
                            return JobStatus(
                                job_id=job_id,
                                status=status,
                                failed=True,
                                completed=True,
                                error_message=f"Job finished with status: {status}",
                            )

                # Wait before next poll
                time.sleep(poll_interval)

            except Exception as e:
                self.logger.warning(
                    "Error checking job status", {"job_id": job_id, "error": str(e)}
                )
                time.sleep(poll_interval)

        # Timeout reached
        self.logger.error(
            "Timeout waiting for job completion",
            {"job_id": job_id, "timeout_seconds": timeout_seconds},
        )

        return JobStatus(
            job_id=job_id,
            status="TIMEOUT",
            failed=True,
            completed=False,
            error_message=f"Timeout after {timeout_seconds} seconds",
        )

    def download_file(self, remote_file_path: str, local_dir: Path) -> DownloadResult:
        """!
        @brief Download a single file from the HPC system.
        @param remote_file_path: The path to the remote file.
        @param local_dir: The local directory to download to.
        @return A DownloadResult indicating success or failure.
        """
        self.logger.debug(
            "Downloading file from HPC",
            {"remote_file": remote_file_path, "local_dir": str(local_dir)},
        )

        try:
            self._ensure_connected()

            if not self._sftp_client:
                return DownloadResult(
                    success=False, error="SFTP client not available"
                )

            # Ensure local directory exists
            local_dir.mkdir(parents=True, exist_ok=True)

            # Extract filename from remote path
            remote_filename = os.path.basename(remote_file_path)
            local_file_path = local_dir / remote_filename

            # Download the file
            self._sftp_client.get(remote_file_path, str(local_file_path))

            self.logger.debug(
                "File downloaded successfully",
                {"remote_file": remote_file_path, "local_file": str(local_file_path)},
            )

            return DownloadResult(success=True)

        except Exception as e:
            error_msg = f"Failed to download file: {e}"
            self.logger.error(
                error_msg,
                {"remote_file": remote_file_path, "local_dir": str(local_dir)},
            )
            return DownloadResult(success=False, error=error_msg)

    def cleanup_remote_directory(self, remote_dir: str) -> bool:
        """!
        @brief Clean up a remote directory and its contents.
        @param remote_dir: The remote directory to clean up.
        @return True if cleanup was successful, False otherwise.
        """
        self.logger.debug("Cleaning up remote directory", {"remote_dir": remote_dir})

        try:
            cleanup_command = f"rm -rf {remote_dir}"
            result = self.execute_remote_command("cleanup", cleanup_command)

            if result.success:
                self.logger.info(
                    "Remote directory cleaned up successfully",
                    {"remote_dir": remote_dir},
                )
                return True
            else:
                self.logger.warning(
                    "Remote directory cleanup failed",
                    {"remote_dir": remote_dir, "error": result.error},
                )
                return False

        except Exception as e:
            self.logger.error(
                "Error during remote cleanup",
                {"remote_dir": remote_dir, "error": str(e)},
            )
            return False

    def __enter__(self):
        """!
        @brief Context manager entry.
        """
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """!
        @brief Context manager exit with cleanup.
        """
        self.disconnect()

    def _mkdir_p(self, sftp: SFTPClient, remote_directory: str):
        """!
        @brief Creates a directory and all its parents recursively on the remote server.
        @param sftp: The SFTP client.
        @param remote_directory: The remote directory to create.
        """
        if remote_directory == "/":
            sftp.chdir("/")
            return
        if remote_directory == "":
            return

        try:
            sftp.chdir(remote_directory)  # sub-directory exists
        except IOError:
            dirname, basename = os.path.split(remote_directory.rstrip("/"))
            self._mkdir_p(sftp, dirname)
            sftp.mkdir(basename)
            sftp.chdir(basename)
            return True
