# =====================================================================================
# Target File: src/handlers/local_handler.py
# Source Reference: src/local_handler.py
# =====================================================================================

from typing import NamedTuple, Optional, Dict, Any
from pathlib import Path

from src.infrastructure.logging_handler import StructuredLogger
from src.infrastructure.process_manager import CommandExecutor
from src.config.settings import Settings
from src.utils.retry_policy import RetryPolicy
from src.domain.errors import ProcessingError

class ExecutionResult(NamedTuple):
    """
    A structured result from subprocess execution.
    
    FROM: Migrated from the ExecutionResult NamedTuple in original `local_handler.py`.
    """
    success: bool
    output: str
    error: str
    return_code: int

class LocalHandler:
    """
    Handles the execution of local command-line interface (CLI) tools.
    
    FROM: Migrated from the original `LocalHandler` class in `local_handler.py`.
    REFACTORING NOTES: Uses injected dependencies (CommandExecutor, RetryPolicy) 
                      instead of creating them internally.
    """
    
    def __init__(self, settings: Settings, logger: StructuredLogger, 
                 command_executor: CommandExecutor, retry_policy: RetryPolicy):
        """
        Initializes the LocalHandler with injected dependencies.
        
        FROM: Original `__init__` method with dependency injection improvements.
        
        Args:
            settings: Application settings
            logger: Logger for recording events
            command_executor: Command execution service
            retry_policy: Retry policy for failed executions
        """
        self.settings = settings
        self.logger = logger
        self.command_executor = command_executor
        self.retry_policy = retry_policy
        
        # Get Python interpreter path from settings
        self.python_interpreter = self._get_python_interpreter()
    
    def _get_python_interpreter(self) -> str:
        """
        Get the Python interpreter path from configuration.
        
        FROM: Python interpreter detection logic from original local_handler.py.
        REFACTORING NOTES: Externalized to configuration instead of hardcoding.
        """
        return self.settings.get_executables().get("python_interpreter", "python3")
    
    def execute_mqi_interpreter(self, case_id: str, case_path: Path, 
                               additional_args: Optional[Dict[str, Any]] = None) -> ExecutionResult:
        """
        Executes the mqi_interpreter (P2) for a given case.
        
        FROM: Migrated from `execute_mqi_interpreter` method in original `local_handler.py`.
        REFACTORING NOTES: Uses injected RetryPolicy instead of hardcoded retry logic.
        
        Args:
            case_id: Case identifier for logging
            case_path: Path to the case directory
            additional_args: Optional additional arguments for the interpreter
            
        Returns:
            ExecutionResult containing execution details
        """
        self.logger.info("Executing MQI interpreter", {
            "case_id": case_id,
            "case_path": str(case_path)
        })
        
        mqi_interpreter_path = self.settings.get_executables().get("mqi_interpreter")
        if not mqi_interpreter_path:
            raise ProcessingError("MQI interpreter path not configured.")

        # Build command arguments
        command = [
            self.python_interpreter,
            mqi_interpreter_path,
            str(case_path)
        ]
        
        # Add additional arguments if provided
        if additional_args:
            for key, value in additional_args.items():
                command.extend([f"--{key}", str(value)])
        
        # Execute with retry policy
        def execute_attempt():
            try:
                result = self.command_executor.execute_command(
                    command=command,
                    cwd=case_path,
                    timeout=self.settings.processing.case_timeout
                )
                
                return ExecutionResult(
                    success=True,
                    output=result.stdout,
                    error=result.stderr,
                    return_code=result.returncode
                )
                
            except ProcessingError as e:
                self.logger.error("MQI interpreter execution failed", {
                    "case_id": case_id,
                    "command": ' '.join(command),
                    "error": str(e)
                })
                
                # Extract return code from error if available
                return_code = getattr(e, 'return_code', -1)
                
                return ExecutionResult(
                    success=False,
                    output="",
                    error=str(e),
                    return_code=return_code
                )
        
        # Apply retry policy
        result = self.retry_policy.execute(
            execute_attempt,
            operation_name="mqi_interpreter",
            context={"case_id": case_id}
        )
        
        if result.success:
            self.logger.info("MQI interpreter completed successfully", {
                "case_id": case_id,
                "output_length": len(result.output)
            })
        else:
            self.logger.error("MQI interpreter failed after retries", {
                "case_id": case_id,
                "return_code": result.return_code,
                "error": result.error
            })
        
        return result
    
    def execute_raw_to_dicom(self, case_id: str, case_path: Path,
                           additional_args: Optional[Dict[str, Any]] = None) -> ExecutionResult:
        """
        Executes the RawToDCM converter (P3) for a given case.
        
        FROM: Migrated from `execute_raw_to_dicom` method in original `local_handler.py`.
        REFACTORING NOTES: Uses injected dependencies and configuration.
        
        Args:
            case_id: Case identifier for logging
            case_path: Path to the case directory  
            additional_args: Optional additional arguments for the converter
            
        Returns:
            ExecutionResult containing execution details
        """
        self.logger.info("Executing Raw to DICOM converter", {
            "case_id": case_id,
            "case_path": str(case_path)
        })
        
        raw_to_dicom_path = self.settings.get_executables().get("raw_to_dicom")
        if not raw_to_dicom_path:
            raise ProcessingError("Raw to DICOM converter path not configured.")

        # Build command arguments
        command = [
            self.python_interpreter,
            raw_to_dicom_path,
            str(case_path)
        ]
        
        # Add additional arguments if provided
        if additional_args:
            for key, value in additional_args.items():
                command.extend([f"--{key}", str(value)])
        
        # Execute with retry policy
        def execute_attempt():
            try:
                result = self.command_executor.execute_command(
                    command=command,
                    cwd=case_path,
                    timeout=self.settings.processing.case_timeout
                )
                
                return ExecutionResult(
                    success=True,
                    output=result.stdout,
                    error=result.stderr,
                    return_code=result.returncode
                )
                
            except ProcessingError as e:
                self.logger.error("Raw to DICOM conversion failed", {
                    "case_id": case_id,
                    "command": ' '.join(command),
                    "error": str(e)
                })
                
                return_code = getattr(e, 'return_code', -1)
                
                return ExecutionResult(
                    success=False,
                    output="",
                    error=str(e),
                    return_code=return_code
                )
        
        # Apply retry policy
        result = self.retry_policy.execute(
            execute_attempt,
            operation_name="raw_to_dicom",
            context={"case_id": case_id}
        )
        
        if result.success:
            self.logger.info("Raw to DICOM conversion completed successfully", {
                "case_id": case_id,
                "output_length": len(result.output)
            })
        else:
            self.logger.error("Raw to DICOM conversion failed after retries", {
                "case_id": case_id,
                "return_code": result.return_code,
                "error": result.error
            })
        
        return result
    
    def validate_case_structure(self, case_path: Path) -> bool:
        """
        Validate that case directory has required structure and files.
        
        FROM: Path validation logic scattered throughout original handlers.
        REFACTORING NOTES: Centralized validation with proper error reporting.
        
        Args:
            case_path: Path to case directory
            
        Returns:
            True if case structure is valid
        """
        self.logger.debug("Validating case structure", {
            "case_path": str(case_path)
        })
        
        try:
            # Check if case path exists and is directory
            if not case_path.exists():
                self.logger.error("Case path does not exist", {"case_path": str(case_path)})
                return False
            
            if not case_path.is_dir():
                self.logger.error("Case path is not a directory", {"case_path": str(case_path)})
                return False
            
            required_file = case_path / "case_config.yaml"
            if not required_file.exists():
                self.logger.warning(f"Required file not found: {required_file}")
                # Depending on strictness, you might want to return False here
            
            return True
            
        except Exception as e:
            self.logger.error("Case structure validation failed", {
                "case_path": str(case_path),
                "error": str(e)
            })
            return False