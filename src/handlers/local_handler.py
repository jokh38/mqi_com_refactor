# =====================================================================================
# Target File: src/handlers/local_handler.py
# Source Reference: src/local_handler.py
# =====================================================================================

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

    def __init__(
        self,
        settings: Settings,
        logger: StructuredLogger,
        command_executor: CommandExecutor,
        retry_policy: RetryPolicy,
    ):
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

    def _convert_windows_path_to_wsl(self, path: str) -> str:
        """
        Convert Windows path to WSL path if running in WSL environment.
        
        Args:
            path: Path string that might be a Windows path
            
        Returns:
            Path converted to WSL format if necessary
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
        """
        config.yaml의 템플릿과 동적 인자를 결합하여 최종 실행 명령어를 생성합니다.

        Args:
            template_name: config.yaml의 command_templates에서 사용할 템플릿 이름
            **kwargs: 템플릿에 전달할 동적 인자들

        Returns:
            subprocess에서 사용할 수 있는 명령어 리스트
        
        Raises:
            ProcessingError: 템플릿을 찾을 수 없거나 포맷팅에 실패한 경우
        """
        try:
            # config.yaml에서 command_templates 가져오기
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
            
            # 동적 인자와 설정의 경로를 결합
            all_format_args = {**converted_executables, **converted_kwargs}
            
            # 템플릿의 플레이스홀더를 실제 값으로 치환
            formatted_command = template.format(**all_format_args)
            
            # 문자열을 subprocess가 사용할 리스트로 안전하게 분리
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
        """
        A generic helper to execute a local command with a retry policy.

        Args:
            case_id: Case identifier for logging.
            case_path: Path to the case directory (CWD for the command).
            command: The command to execute as a list of strings.
            operation_name: A unique name for the operation (for retry policy).
            log_message: The message to log for this operation.

        Returns:
            ExecutionResult containing the outcome of the execution.
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
        """
        Executes the mqi_interpreter using a generalized command runner.
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
        """
        Executes the RawToDCM converter using a generalized command runner.
        """
        return self._execute_command_with_retry(
            case_id=case_id,
            case_path=case_path,
            command=command,
            operation_name="raw_to_dicom",
            log_message="Executing Raw to DICOM converter",
        )

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
        self, beam_directory: Path, output_dir: Path
    ) -> ExecutionResult:
        """
        mqi_interpreter 실행을 위한 Wrapper 메서드.
        템플릿에 필요한 동적 인자를 정의하고, 명령어 생성을 위임합니다.

        Args:
            beam_directory: Path to the beam directory (used as --logdir).
            output_dir: Path to the output directory for generated files.

        Returns:
            ExecutionResult containing execution details.
        """
        dynamic_args = {
            "beam_directory": str(beam_directory),
            "output_dir": str(output_dir),
        }

        # 범용 빌더를 호출하여 명령어 생성
        command_to_execute = self._build_command_from_template(
            "mqi_interpreter", **dynamic_args
        )
        
        case_id = beam_directory.parent.name
        # execute_mqi_interpreter는 이제 미리 빌드된 명령어를 받아 실행만 담당
        return self.execute_mqi_interpreter(case_id, beam_directory, command_to_execute)

    def run_raw_to_dcm(
        self, input_file: Path, output_dir: Path, case_path: Path
    ) -> ExecutionResult:
        """
        RawToDCM 실행을 위한 Wrapper 메서드.
        템플릿에 필요한 동적 인자를 정의하고, 명령어 생성을 위임합니다.

        Args:
            input_file: Input .raw file
            output_dir: Output directory for DCM files
            case_path: Case directory path

        Returns:
            ExecutionResult containing execution details
        """
        dynamic_args = {
            "input_file": str(input_file),
            "output_dir": str(output_dir),
        }

        # 범용 빌더를 호출하여 명령어 생성
        command_to_execute = self._build_command_from_template(
            "raw_to_dicom", **dynamic_args
        )
        
        case_id = case_path.name  # Use directory name as case_id
        # execute_raw_to_dicom는 이제 미리 빌드된 명령어를 받아 실행만 담당
        return self.execute_raw_to_dicom(case_id, case_path, command_to_execute)
