import sys
from pathlib import Path
import logging

# 테스트 스크립트가 src 폴더 내부의 모듈을 찾을 수 있도록 경로를 추가합니다.
project_root = Path(__file__).parent.resolve()
src_path = project_root / "mqi_communicator0905" / "src"
sys.path.insert(0, str(project_root / "mqi_communicator0905"))

try:
    # 리팩토링된 구조에 따라 필요한 모듈을 임포트합니다.
    # 실제 `worker.py`에 `run_worker`와 같은 진입점 함수가 있다고 가정합니다.
    from src.config.settings import ConfigManager
    from src.core.worker import run_worker
except ImportError as e:
    print(f"필수 모듈을 임포트하는 데 실패했습니다: {e}")
    print(f"프로젝트 구조를 확인하거나 PYTHONPATH를 설정해주세요. 현재 경로: {sys.path}")
    sys.exit(1)


def main():
    """
    디렉터리 스캔을 건너뛰고 특정 케이스에 대해 워커를 직접 실행하는 테스트 스크립트입니다.
    """
    # --- 1. 테스트 설정 (요청에 따라 경로 하드코딩) ---
    # 참고: Windows 경로에서는 raw string(r"...")을 사용하거나 슬래시(/)를 사용하세요.
    CASE_PATH = Path(r"C:\MOQUI_SMC\data\log_SHI\1.2.840.113854.19.1.19271.1")
    INTERPRETER_SCRIPT_PATH = str(Path(r"C:\MOQUI_SMC\mqi_interpreter\main_cli.py"))
    CONFIG_FILE_PATH = project_root / "config" / "config.yaml"

    # 테스트를 위한 기본 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        stream=sys.stdout
    )
    logger = logging.getLogger("TestLauncher")

    logger.info("--- 워커 실행 테스트 스크립트 시작 ---")
    logger.info(f"사용할 설정 파일: {CONFIG_FILE_PATH}")
    logger.info(f"대상 케이스 경로: {CASE_PATH}")

    if not CASE_PATH.exists() or not CASE_PATH.is_dir():
        logger.error(f"오류: 케이스 경로가 존재하지 않거나 디렉터리가 아닙니다: {CASE_PATH}")
        return

    # --- 2. 설정 로드 및 수정 ---
    try:
        # YAML 파일에서 기본 설정을 로드합니다.
        config_manager = ConfigManager(config_path=str(CONFIG_FILE_PATH))
        settings = config_manager.get_config()

        # 요청에 따라 mqi_interpreter 경로를 메모리에서 직접 덮어씁니다.
        # 이는 `fix_error3.md`에서 제안된 `_script` 접미사를 사용하는 구조를 따릅니다.
        logger.info(f"기존 인터프리터 경로: {settings.executables.mqi_interpreter_script}")
        settings.executables.mqi_interpreter_script = INTERPRETER_SCRIPT_PATH
        logger.info(f"덮어쓴 인터프리터 경로: {settings.executables.mqi_interpreter_script}")

        # `config.yaml`에 `command_templates` 섹션이 없을 경우를 대비해 기본값을 설정합니다.
        if not settings.command_templates.get('mqi_interpreter'):
            logger.warning("`command_templates.mqi_interpreter`를 config.yaml에서 찾을 수 없습니다. 테스트를 위해 기본 템플릿을 사용합니다.")
            template = "{python_interpreter} {mqi_interpreter_script} --logdir {beam_directory} --outputdir {output_dir}"
            settings.command_templates['mqi_interpreter'] = template

    except Exception as e:
        logger.error(f"설정 파일을 로드하거나 수정하는 중 오류 발생: {e}", exc_info=True)
        return

    # --- 3. 워커 실행 ---
    try:
        logger.info("워커를 초기화하고 케이스 처리를 시작합니다...")
        # `src/core/worker.py`에 `run_worker` 함수가 설정과 케이스 경로를 인자로 받아
        # 전체 워크플로우를 처리한다고 가정합니다.
        run_worker(settings=settings, case_path=CASE_PATH)
        logger.info(f"워커가 케이스 처리를 완료했습니다: {CASE_PATH.name}")

    except NameError:
        logger.error("`run_worker` 함수를 찾을 수 없습니다. `src.core.worker`에 해당 함수가 정의되어 있는지 확인해주세요.")
    except Exception as e:
        logger.error(f"워커 실행 중 예외 발생: {e}", exc_info=True)

    logger.info("--- 워커 실행 테스트 스크립트 종료 ---")


if __name__ == "__main__":
    main()