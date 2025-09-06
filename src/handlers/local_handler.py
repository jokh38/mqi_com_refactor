# =====================================================================================
# Target File: src/handlers/local_handler.py
# Source Reference: src/local_handler.py
# =====================================================================================

from typing import NamedTuple, Optional, Dict, Any
from pathlib import Path
import shlex

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
            
            # 동적 인자와 설정의 경로를 결합
            all_format_args = {**executables, **kwargs}
            
            # 템플릿의 플레이스홀더를 실제 값으로 치환
            formatted_command = template.format(**all_format_args)
            
            # 문자열을 subprocess가 사용할 리스트로 안전하게 분리
            return shlex.split(formatted_command)
            
        except KeyError as e:
            raise ProcessingError(f"Missing template argument: {e}")
        except Exception as e:
            raise ProcessingError(f"Failed to build command from template '{template_name}': {e}")

    def execute_mqi_interpreter(
        self,
        case_id: str,
        case_path: Path,
        command: list[str],  # additional_args 대신 완성된 command 리스트를 받음
    ) -> ExecutionResult:
        """
        미리 생성된 명령어를 사용하여 mqi_interpreter를 실행합니다.

        FROM: Migrated from `execute_mqi_interpreter` method in original `local_handler.py`.
        REFACTORING NOTES: Uses injected RetryPolicy instead of hardcoded retry logic.
                          Now accepts pre-built command instead of building it internally.

        Args:
            case_id: Case identifier for logging
            case_path: Path to the case directory
            command: Pre-built command list to execute

        Returns:
            ExecutionResult containing execution details
        """
        self.logger.info(
            "Executing MQI interpreter",
            {"case_id": case_id, "command": " ".join(command)},
        )

        # 내부에서 명령어를 조립하는 로직은 모두 제거됨

        # Execute with retry policy
        def execute_attempt():
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
                log_msg = "MQI interpreter execution failed"
                log_ctx = {
                    "case_id": case_id,
                    "command": " ".join(command),
                    "error": str(e),
                }
                self.logger.error(log_msg, log_ctx)

                # Extract return code from error if available
                return_code = getattr(e, "return_code", -1)

                return ExecutionResult(
                    success=False, output="", error=str(e), return_code=return_code
                )

        # Apply retry policy
        result = self.retry_policy.execute(
            execute_attempt,
            operation_name="mqi_interpreter",
            context={"case_id": case_id},
        )

        if result.success:
            self.logger.info(
                "MQI interpreter completed successfully",
                {"case_id": case_id, "output_length": len(result.output)},
            )
        else:
            self.logger.error(
                "MQI interpreter failed after retries",
                {
                    "case_id": case_id,
                    "return_code": result.return_code,
                    "error": result.error,
                },
            )  # noqa: E501

        return result

    def execute_raw_to_dicom(
        self,
        case_id: str,
        case_path: Path,
        additional_args: Optional[Dict[str, Any]] = None,
    ) -> ExecutionResult:
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
        self.logger.info(
            "Executing Raw to DICOM converter",
            {"case_id": case_id, "case_path": str(case_path)},
        )

        raw_to_dicom_path = self.settings.get_executables().get("raw_to_dicom")
        if not raw_to_dicom_path:
            raise ProcessingError("Raw to DICOM converter path not configured.")

        # Build command arguments
        command = [self.python_interpreter, raw_to_dicom_path, str(case_path)]

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
                    timeout=self.settings.processing.case_timeout,
                )

                return ExecutionResult(
                    success=True,
                    output=result.stdout,
                    error=result.stderr,
                    return_code=result.returncode,
                )

            except ProcessingError as e:
                log_msg = "Raw to DICOM conversion failed"
                log_ctx = {
                    "case_id": case_id,
                    "command": " ".join(command),
                    "error": str(e),
                }
                self.logger.error(log_msg, log_ctx)

                return_code = getattr(e, "return_code", -1)

                return ExecutionResult(
                    success=False, output="", error=str(e), return_code=return_code
                )

        # Apply retry policy
        result = self.retry_policy.execute(
            execute_attempt, operation_name="raw_to_dicom", context={"case_id": case_id}
        )

        if result.success:
            self.logger.info(
                "Raw to DICOM conversion completed successfully",
                {"case_id": case_id, "output_length": len(result.output)},
            )
        else:
            self.logger.error(
                "Raw to DICOM conversion failed after retries",
                {
                    "case_id": case_id,
                    "return_code": result.return_code,
                    "error": result.error,
                },
            )  # noqa: E501

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
        Wrapper method for running RawToDCM with specific input/output paths.

        Args:
            input_file: Input .raw file
            output_dir: Output directory for DCM files
            case_path: Case directory path

        Returns:
            ExecutionResult containing execution details
        """
        additional_args = {"input": str(input_file), "output": str(output_dir)}

        case_id = case_path.name  # Use directory name as case_id
        return self.execute_raw_to_dicom(case_id, case_path, additional_args)
