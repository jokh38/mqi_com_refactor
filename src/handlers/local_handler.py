# =====================================================================================
# Target File: src/handlers/local_handler.py
# Source Reference: src/local_handler.py
# =====================================================================================
"""!
@file local_handler.py
@brief Handles the execution of local command-line interface (CLI) tools.
"""

from typing import NamedTuple, Optional, Dict, Any
from pathlib import Path
import shlex
import platform

from src.infrastructure.logging_handler import StructuredLogger
from src.infrastructure.process_manager import CommandExecutor
from src.config.settings import Settings
from src.utils.retry_policy import RetryPolicy
from src.domain.errors import ProcessingError


class ExecutionResult(NamedTuple):
    """!
    @brief A structured result from subprocess execution.
    """

    success: bool
    output: str
    error: str
    return_code: int


class LocalHandler:
    """!
    @brief Handles the execution of local command-line interface (CLI) tools.
    @details This class uses injected dependencies (CommandExecutor, RetryPolicy)
             to execute commands with a retry policy.
    """

    def __init__(
        self,
        settings: Settings,
        logger: StructuredLogger,
        command_executor: CommandExecutor,
        retry_policy: RetryPolicy,
    ):
        """!
        @brief Initializes the LocalHandler with injected dependencies.
        @param settings: Application settings.
        @param logger: Logger for recording events.
        @param command_executor: Command execution service.
        @param retry_policy: Retry policy for failed executions.
        """
        self.settings = settings
        self.logger = logger
        self.command_executor = command_executor
        self.retry_policy = retry_policy

        # Get Python interpreter path from settings
        self.python_interpreter = self._get_python_interpreter()

    def _get_python_interpreter(self) -> str:
        """!
        @brief Get the Python interpreter path from configuration.
        @return The path to the Python interpreter.
        """
        return self.settings.get_executables().get("python_interpreter", "python3")

    def _convert_windows_path_to_wsl(self, path: str) -> str:
        """!
        @brief Convert a Windows path to a WSL path if running in a WSL environment.
        @param path: The path string that might be a Windows path.
        @return The path converted to WSL format if necessary.
        """
        # Check if we're running in WSL
        if platform.system() == "Linux" and "microsoft" in platform.release().lower():
            # Convert Windows path to WSL path
            if path.startswith("C:"):
                return path.replace("C:", "/mnt/c").replace("\\", "/")
            elif path.startswith("D:"):
                return path.replace("D:", "/mnt/d").replace("\\", "/")
            # Add more drive letters as needed
        return path

    def _build_command_from_template(self, template_name: str, **kwargs) -> list[str]:
        """!
        @brief Builds the final execution command by combining a template from config.yaml with dynamic arguments.
        @param template_name: The name of the template to use from command_templates in config.yaml.
        @param **kwargs: Dynamic arguments to pass to the template.
        @return A list of strings representing the command, suitable for use with subprocess.
        @raises ProcessingError: If the template cannot be found or formatting fails.
        """
        try:
            # Get command_templates from config.yaml
            command_templates = getattr(self.settings, 'command_templates', {})
            if template_name not in command_templates:
                raise ProcessingError(f"Command template '{template_name}' not found in config.yaml")
            
            template = command_templates[template_name]
            executables = self.settings.get_executables()
            
            # Convert Windows paths to WSL paths for all executables if running in WSL
            converted_executables = {}
            for key, value in executables.items():
                converted_executables[key] = self._convert_windows_path_to_wsl(value)
            
            # Convert Windows paths in kwargs as well
            converted_kwargs = {}
            for key, value in kwargs.items():
                if isinstance(value, str):
                    converted_kwargs[key] = self._convert_windows_path_to_wsl(value)
                else:
                    converted_kwargs[key] = value
            
            # Combine dynamic arguments and configured paths
            all_format_args = {**converted_executables, **converted_kwargs}
            
            # Replace placeholders in the template with actual values
            formatted_command = template.format(**all_format_args)
            
            # Safely split the string into a list for subprocess
            return shlex.split(formatted_command)
            
        except KeyError as e:
            raise ProcessingError(f"Missing template argument: {e}")
        except Exception as e:
            raise ProcessingError(f"Failed to build command from template '{template_name}': {e}")

    def _execute_command_with_retry(
        self,
        case_id: str,
        case_path: Path,
        command: list[str],
        operation_name: str,
        log_message: str,
    ) -> ExecutionResult:
        """!
        @brief A generic helper to execute a local command with a retry policy.
        @param case_id: Case identifier for logging.
        @param case_path: Path to the case directory (CWD for the command).
        @param command: The command to execute as a list of strings.
        @param operation_name: A unique name for the operation (for retry policy).
        @param log_message: The message to log for this operation.
        @return ExecutionResult containing the outcome of the execution.
        """
        self.logger.info(
            log_message,
            {"case_id": case_id, "command": " ".join(command)},
        )

        def execute_attempt() -> ExecutionResult:
            try:
                result = self.command_executor.execute_command(
                    command=command,
                    cwd=case_path,
                    timeout=self.settings.processing.case_timeout,
                )
                return ExecutionResult(
                    success=True,
                    output=result.stdout,
                    error=result.stderr,
                    return_code=result.returncode,
                )
            except ProcessingError as e:
                log_ctx = {
                    "case_id": case_id,
                    "command": " ".join(command),
                    "error": str(e),
                }
                self.logger.error(f"{operation_name} execution failed", log_ctx)
                return_code = getattr(e, "return_code", -1)
                return ExecutionResult(
                    success=False, output="", error=str(e), return_code=return_code
                )

        result = self.retry_policy.execute(
            execute_attempt,
            operation_name=operation_name,
            context={"case_id": case_id},
        )

        if result.success:
            self.logger.info(
                f"{operation_name} completed successfully",
                {"case_id": case_id, "output_length": len(result.output)},
            )
        else:
            self.logger.error(
                f"{operation_name} failed after retries",
                {
                    "case_id": case_id,
                    "return_code": result.return_code,
                    "error": result.error,
                },
            )

        return result

    def execute_mqi_interpreter(
        self,
        case_id: str,
        case_path: Path,
        command: list[str],
    ) -> ExecutionResult:
        """!
        @brief Executes the mqi_interpreter using a generalized command runner.
        @param case_id: The case identifier for logging.
        @param case_path: The path to the case directory.
        @param command: The command to execute.
        @return An ExecutionResult containing the outcome.
        """
        return self._execute_command_with_retry(
            case_id=case_id,
            case_path=case_path,
            command=command,
            operation_name="mqi_interpreter",
            log_message="Executing MQI interpreter",
        )

    def execute_raw_to_dicom(
        self,
        case_id: str,
        case_path: Path,
        command: list[str],
    ) -> ExecutionResult:
        """!
        @brief Executes the RawToDCM converter using a generalized command runner.
        @param case_id: The case identifier for logging.
        @param case_path: The path to the case directory.
        @param command: The command to execute.
        @return An ExecutionResult containing the outcome.
        """
        return self._execute_command_with_retry(
            case_id=case_id,
            case_path=case_path,
            command=command,
            operation_name="raw_to_dicom",
            log_message="Executing Raw to DICOM converter",
        )

    def validate_case_structure(self, case_path: Path) -> bool:
        """!
        @brief Validate that the case directory has the required structure and files.
        @param case_path: Path to the case directory.
        @return True if the case structure is valid, False otherwise.
        """
        self.logger.debug("Validating case structure", {"case_path": str(case_path)})

        try:
            # Check if case path exists and is directory
            if not case_path.exists():
                self.logger.error(
                    "Case path does not exist", {"case_path": str(case_path)}
                )
                return False

            if not case_path.is_dir():
                self.logger.error(
                    "Case path is not a directory", {"case_path": str(case_path)}
                )
                return False

            required_file = case_path / "case_config.yaml"
            if not required_file.exists():
                self.logger.warning(f"Required file not found: {required_file}")
                # Depending on strictness, you might want to return False here

            return True

        except Exception as e:
            self.logger.error(
                "Case structure validation failed",
                {"case_path": str(case_path), "error": str(e)},
            )
            return False

    def run_mqi_interpreter(
        self, beam_directory: Path, output_dir: Path, case_id: Optional[str] = None
    ) -> ExecutionResult:
        """!
        @brief Wrapper method for running the mqi_interpreter.
        @details Defines the dynamic arguments needed for the template and delegates command creation.
        @param beam_directory: Path to the beam directory (or case directory).
        @param output_dir: Path to the output directory for generated files.
        @param case_id: Optional case_id. If not provided, it's inferred from the parent directory.
        @return ExecutionResult containing execution details.
        """
        dynamic_args = {
            "beam_directory": str(beam_directory),
            "output_dir": str(output_dir),
        }

        # Call the generic builder to create the command
        command_to_execute = self._build_command_from_template(
            "mqi_interpreter", **dynamic_args
        )
        
        # If case_id is not provided, infer it from the parent directory (for beam-level calls)
        # Otherwise, use the provided case_id (for case-level calls)
        id_to_use = case_id if case_id is not None else beam_directory.parent.name

        # execute_mqi_interpreter now only takes the pre-built command and executes it
        return self.execute_mqi_interpreter(id_to_use, beam_directory, command_to_execute)

    def run_raw_to_dcm(
        self, input_file: Path, output_dir: Path, case_path: Path
    ) -> ExecutionResult:
        """!
        @brief Wrapper method for running RawToDCM.
        @details Defines the dynamic arguments needed for the template and delegates command creation.
        @param input_file: Input .raw file.
        @param output_dir: Output directory for DCM files.
        @param case_path: Case directory path.
        @return ExecutionResult containing execution details.
        """
        dynamic_args = {
            "input_file": str(input_file),
            "output_dir": str(output_dir),
        }

        # Call the generic builder to create the command
        command_to_execute = self._build_command_from_template(
            "raw_to_dicom", **dynamic_args
        )
        
        case_id = case_path.name  # Use directory name as case_id
        # execute_raw_to_dicom now only takes the pre-built command and executes it
        return self.execute_raw_to_dicom(case_id, case_path, command_to_execute)
