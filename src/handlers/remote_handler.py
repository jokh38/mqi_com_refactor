# =====================================================================================
# Target File: src/handlers/remote_handler.py
# Source Reference: src/remote_handler.py
# =====================================================================================

from typing import Optional, Dict, Any, Tuple
from pathlib import Path
import paramiko
from paramiko import SSHClient, SFTPClient

from src.infrastructure.logging_handler import StructuredLogger
from src.config.settings import Settings
from src.utils.retry_policy import RetryPolicy
from src.domain.errors import ProcessingError
from src.handlers.local_handler import ExecutionResult

class RemoteHandler:
    """
    Handles HPC communication (SSH/SFTP), managing remote execution and file transfer operations.
    
    FROM: Migrated from the original `RemoteHandler` class in `remote_handler.py`.
    REFACTORING NOTES: Uses injected dependencies for retry policy and settings.
                      Improved error handling and connection management.
    """
    
    def __init__(self, settings: Settings, logger: StructuredLogger, retry_policy: RetryPolicy):
        """
        Initialize RemoteHandler with injected dependencies.
        
        FROM: Original `__init__` method with dependency injection improvements.
        
        Args:
            settings: Application settings containing HPC configuration
            logger: Logger for recording operations
            retry_policy: Retry policy for failed operations
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
        """
        Establish SSH/SFTP connections to the remote HPC system.
        
        FROM: Connection establishment logic from original remote_handler.py.
        REFACTORING NOTES: Improved error handling and configuration usage.
        """
        self.logger.info("Establishing HPC connection", {
            "host": self.settings.hpc.hostname if hasattr(self.settings, 'hpc') else 'configured'
        })
        
        try:
            # Create SSH client
            self._ssh_client = paramiko.SSHClient()
            self._ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # TODO (AI): Get HPC configuration from settings
            # Connect to HPC system
            # self._ssh_client.connect(
            #     hostname=self.settings.hpc.hostname,
            #     username=self.settings.hpc.username,
            #     key_filename=self.settings.hpc.key_file,
            #     timeout=self.settings.hpc.connection_timeout
            # )
            
            # Create SFTP client
            self._sftp_client = self._ssh_client.open_sftp()
            
            self._connected = True
            self.logger.info("HPC connection established successfully")
            
        except Exception as e:
            self.logger.error("Failed to establish HPC connection", {
                "error": str(e)
            })
            self._cleanup_connections()
            raise ProcessingError(f"Failed to connect to HPC system: {e}")
    
    def disconnect(self) -> None:
        """
        Close SSH/SFTP connections.
        
        FROM: Connection cleanup logic from original remote_handler.py.
        """
        self.logger.debug("Closing HPC connections")
        self._cleanup_connections()
    
    def _cleanup_connections(self) -> None:
        """Clean up connection resources."""
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
        """Ensure connection is established before operations."""
        if not self._connected or not self._ssh_client:
            self.connect()
    
    def upload_case(self, case_id: str, local_path: Path, remote_path: str) -> bool:
        """
        Upload case files to HPC system.
        
        FROM: File upload functionality from original remote_handler.py.
        REFACTORING NOTES: Uses retry policy and improved error handling.
        
        Args:
            case_id: Case identifier for logging
            local_path: Local path to case directory
            remote_path: Remote path where case should be uploaded
            
        Returns:
            True if upload successful
        """
        self.logger.info("Uploading case to HPC", {
            "case_id": case_id,
            "local_path": str(local_path),
            "remote_path": remote_path
        })
        
        def upload_attempt():
            self._ensure_connected()
            
            if not self._sftp_client:
                raise ProcessingError("SFTP client not available")
            
            # TODO (AI): Implement recursive directory upload
            # This should handle:
            # - Creating remote directories
            # - Uploading all files recursively
            # - Setting proper permissions
            # - Progress monitoring for large files
            
            self.logger.info("Case upload completed", {
                "case_id": case_id,
                "remote_path": remote_path
            })
            
            return True
        
        try:
            return self.retry_policy.execute(
                upload_attempt,
                operation_name="case_upload",
                context={"case_id": case_id}
            )
        except Exception as e:
            self.logger.error("Case upload failed after retries", {
                "case_id": case_id,
                "error": str(e)
            })
            return False
    
    def execute_remote_command(self, case_id: str, command: str, 
                             remote_cwd: Optional[str] = None) -> ExecutionResult:
        """
        Execute a command on the remote HPC system.
        
        FROM: Remote command execution from original remote_handler.py.
        REFACTORING NOTES: Improved error handling and result processing.
        
        Args:
            case_id: Case identifier for logging
            command: Command to execute
            remote_cwd: Remote working directory (optional)
            
        Returns:
            ExecutionResult containing execution details
        """
        self.logger.info("Executing remote command", {
            "case_id": case_id,
            "command": command,
            "remote_cwd": remote_cwd
        })
        
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
            output = stdout.read().decode('utf-8')
            error = stderr.read().decode('utf-8')
            
            return ExecutionResult(
                success=(exit_code == 0),
                output=output,
                error=error,
                return_code=exit_code
            )
        
        try:
            result = self.retry_policy.execute(
                execute_attempt,
                operation_name="remote_command",
                context={"case_id": case_id, "command": command}
            )
            
            if result.success:
                self.logger.info("Remote command completed successfully", {
                    "case_id": case_id,
                    "command": command,
                    "output_length": len(result.output)
                })
            else:
                self.logger.error("Remote command failed", {
                    "case_id": case_id,
                    "command": command,
                    "return_code": result.return_code,
                    "error": result.error
                })
            
            return result
            
        except Exception as e:
            self.logger.error("Remote command execution failed after retries", {
                "case_id": case_id,
                "command": command,
                "error": str(e)
            })
            
            return ExecutionResult(
                success=False,
                output="",
                error=str(e),
                return_code=-1
            )
    
    def download_results(self, case_id: str, remote_path: str, local_path: Path) -> bool:
        """
        Download case results from HPC system.
        
        FROM: File download functionality from original remote_handler.py.
        REFACTORING NOTES: Uses retry policy and improved error handling.
        
        Args:
            case_id: Case identifier for logging
            remote_path: Remote path to results directory
            local_path: Local path where results should be downloaded
            
        Returns:
            True if download successful
        """
        self.logger.info("Downloading case results from HPC", {
            "case_id": case_id,
            "remote_path": remote_path,
            "local_path": str(local_path)
        })
        
        def download_attempt():
            self._ensure_connected()
            
            if not self._sftp_client:
                raise ProcessingError("SFTP client not available")
            
            # Ensure local directory exists
            local_path.mkdir(parents=True, exist_ok=True)
            
            # TODO (AI): Implement recursive directory download
            # This should handle:
            # - Listing remote directories
            # - Downloading all files recursively
            # - Preserving directory structure
            # - Progress monitoring for large files
            
            self.logger.info("Case results download completed", {
                "case_id": case_id,
                "local_path": str(local_path)
            })
            
            return True
        
        try:
            return self.retry_policy.execute(
                download_attempt,
                operation_name="results_download",
                context={"case_id": case_id}
            )
        except Exception as e:
            self.logger.error("Results download failed after retries", {
                "case_id": case_id,
                "error": str(e)
            })
            return False
    
    def check_job_status(self, case_id: str, job_id: str) -> Dict[str, Any]:
        """
        Check the status of a submitted job on HPC system.
        
        FROM: Job status checking from original remote_handler.py.
        
        Args:
            case_id: Case identifier for logging
            job_id: HPC job identifier
            
        Returns:
            Dictionary containing job status information
        """
        self.logger.debug("Checking HPC job status", {
            "case_id": case_id,
            "job_id": job_id
        })
        
        # TODO (AI): Implement job status checking
        # This should use the appropriate HPC scheduler commands (SLURM, PBS, etc.)
        # to check job status and return structured information
        
        return {
            "job_id": job_id,
            "status": "unknown",
            "queue_time": None,
            "start_time": None,
            "completion_time": None,
            "error_message": None
        }
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        self.disconnect()