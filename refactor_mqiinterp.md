# 리팩토링 계획: 개별 Beam Worker 및 HPC 잡 분리 (Full Version)

## 1. 목표

현재 `mqi-communicator`는 신규 Case 폴더를 단일 작업 단위로 처리한다. 이 구조를 변경하여, 신규 Case 폴더 내에 있는 각 **하위 폴더(Beam)를 개별적인 작업(Worker)으로 분리하여 독립적으로 처리**하도록 리팩토링한다. 이에는 로컬에서의 전처리뿐만 아니라, **HPC로의 데이터 전송 및 `mqi_simulation` 실행을 각 Beam 단위로 분리**하는 것을 포함한다.

이를 통해 얻는 기대효과는 다음과 같다.
*   각 Beam의 처리 과정을 로컬부터 HPC 시뮬레이션까지 개별적으로 추적하고 상태를 관리할 수 있다.
*   Rich Display에 각 Beam(Worker)별 GPU 할당 및 HPC 잡 진행 상황을 시각적으로 표시할 수 있다.
*   Beam 단위의 완전한 병렬 처리를 통해 전체 처리 효율을 극대화할 수 있다.

## 2. 분석: As-Is vs. To-Be

| 구분 | As-Is (현재 구조) | To-Be (목표 구조) |
| --- | --- | --- |
| **작업 단위** | Case 폴더 1개 = Worker 1개 | Case 폴더 내 Beam 폴더 1개 = Worker 1개 |
| **탐지 주체** | `main.py`가 Case 폴더 탐지 | `WorkflowManager` (Dispatcher)가 Beam 폴더들 탐지 |
| **Worker 생성** | `ProcessManager`가 Case 단위로 단일 Worker 생성 | `WorkflowManager`가 Beam 단위로 다중 Worker 생성 요청 |
| **상태 관리** | `CaseRepository`가 Case 단위 상태 관리 | `CaseRepository`가 Beam 단위의 세분화된 상태를 관리하도록 확장 |
| **HPC 파일 전송** | Case 전체에 대한 결과물(`*.csv`)을 단일 폴더에 업로드 | 각 Beam Worker가 자신의 결과물(**다수의 `*.csv` 파일들**)을 HPC의 개별 Beam 폴더에 업로드 |
| **HPC 시뮬레이션**| Case 전체에 대해 `mqi_simulation` 잡 1개 실행 | 각 Beam에 대해 `mqi_simulation` 잡 1개씩 개별 실행 |
| **HPC 결과 취합** | 시뮬레이션 결과(`output.raw`)를 Case 폴더로 다운로드 | 각 Beam의 시뮬레이션 결과(**단일 `raw` 파일**)를 **`config.yaml`에 지정된 로컬 폴더** 하위의 Beam 폴더로 다운로드 |
| **UI 표시** | Case 1개에 대한 진행 상황 표시 | 여러 Beam 각각에 대한 진행 상황 및 GPU/HPC 잡 상태 표시 |

## 3. 상세 수정 계획

### 3.1. `src/core/workflow_manager.py` 수정 (Dispatcher 역할)

최상위 `WorkflowManager`는 더 이상 단일 Case의 전체 플로우를 관리하지 않는다. 대신, **"Case를 받아 Beam들을 분리하고, 각 Beam에 대한 Worker 생성을 지시하는 Dispatcher"** 역할로 변경되어야 한다.

1.  **`dispatch_beams_as_workers` 메서드 구현**:
    *   이 메서드는 `case_id`와 `case_path`를 인자로 받는다.
    *   `case_path` 내의 모든 하위 디렉터리(Beam)를 스캔한다.
    *   각 Beam 폴더에 대해 `ProcessManager`를 통해 `worker_main`을 실행하는 자식 프로세스를 생성하도록 요청한다.
    *   이때 `beam_id` (예: `{case_id}_{beam_name}`)와 `beam_path`를 `worker_main`에 전달한다.
    *   DB에 부모 Case의 상태를 `PROCESSING`으로 업데이트하고, 각 Beam에 대한 레코드를 새로 생성한다.

### 3.2. `src/core/worker.py` (`worker_main` 함수) 수정

`worker_main` 함수는 이제 단일 Beam의 처리를 담당한다.

*   **함수 시그니처 변경**: `case_id`, `case_path` 대신 `beam_id`, `beam_path`를 인자로 받도록 수정한다.
*   **내부 로직**: `worker_main` 내부 로직은 크게 변경할 필요가 없다. 기존과 동일하게 DB 연결, Repository 생성, `WorkflowManager` 인스턴스 생성 및 실행의 흐름을 따른다. 단, 생성된 `WorkflowManager`는 이제 단일 Beam의 생명주기를 관리하며, 모든 DB 업데이트와 파일 처리는 `beam_id`와 `beam_path`를 기준으로 수행한다.

### 3.3. `main.py` 또는 진입점 스크립트 수정

애플리케이션의 진입점은 Case를 탐지한 후 Worker가 아닌 Dispatcher를 실행해야 한다.

1.  **신규 Case 탐지**: 기존의 신규 Case 폴더 탐지 로직은 유지한다.
2.  **Dispatcher 프로세스 실행**: 탐지된 `case_path`에 대해 `ProcessManager`를 사용하여 새로운 "Dispatcher" 프로세스를 시작한다. 이 프로세스는 `WorkflowManager`를 초기화하고 `dispatch_beams_as_workers` 메서드를 실행하는 단일 목적을 가진다.

### 3.4. `src/repositories/case_repo.py` 및 DB 스키마 수정

Beam 단위의 상태 추적을 위해 데이터베이스 구조를 확장해야 한다.

*   **DB 스키마 확장**: `beams` 테이블을 새로 만드는 것을 권장한다. 이 테이블에는 `beam_id` (Primary Key), `parent_case_id` (Foreign Key to `cases`), `beam_path`, `status`, `gpu_id`, `hpc_job_id`, `created_at`, `updated_at` 등의 컬럼이 포함되어야 한다.
*   **`CaseRepository` 확장**: `beams` 테이블에 대한 CRUD(Create, Read, Update, Delete) 작업을 수행할 메서드를 추가한다. (예: `create_beam_record`, `update_beam_status_by_id`, `get_beam_by_id`)

### 3.5. `src/domain/states.py` 수정 (Worker 내부 상태)

Beam Worker 내부에서 실행될 `WorkflowManager`의 상태(State)들이 HPC와 상호작용하는 방식을 수정해야 한다.

1.  **`FileUploadState` 수정**:
    *   `mqi_interpreter` 실행 결과로 생성된 **해당 Beam 폴더 내의 모든 `*.csv` 파일들과 개별 `moqui_tps.in` 파일**을 HPC에 업로드하도록 변경한다.
    *   **각 Beam은 자신만의 `moqui_tps.in` 파일을 가져야 한다** - 이는 `mqi_interpreter` 실행 시 각 Beam별로 생성되거나 복사되어야 한다.
    *   HPC의 업로드 경로는 Beam 단위의 개별 폴더로 지정한다. (예: `/remote/path/{case_id}/{beam_id}/`)

2.  **`HpcExecutionState` 수정**:
    *   `submit_simulation_job` 호출 시, `beam_id`를 전달한다.
    *   HPC에서 실행될 `mqi_simulation` 명령어는 업로드된 **다수의 CSV 파일들과 해당 Beam의 `moqui_tps.in` 파일을 입력으로 받아 단일 `raw` 파일을 생성**한다. 명령어의 입력 경로가 Beam의 개별 원격 경로를 가리키도록 수정해야 한다.
    *   반환된 `job_id`를 `CaseRepository`를 통해 해당 Beam의 레코드에 저장한다.

3.  **`DownloadState` 수정**:
    *   시뮬레이션 결과물인 **단일 `raw` 파일** (예: `output.raw`)을 원격 Beam 폴더에서 로컬로 다운로드하도록 경로를 수정한다.
    *   다운로드될 로컬 경로는 **`config.yaml` 파일에 정의된 결과 폴더**를 기반으로 동적으로 결정되어야 한다. (예: `{config.result_path}/{case_id}/{beam_id}/output.raw`)

### 3.6. `src/handlers/remote_handler.py` 수정

`RemoteHandler`의 메서드들은 대부분 재사용 가능하지만, 호출 방식과 인자를 Beam에 맞게 조정해야 한다.

1.  **`submit_simulation_job` 메서드 수정**:
    *   HPC 잡 스케줄러(예: Slurm)의 잡 이름에 `beam_id`를 포함시켜(`sbatch --job-name=moqui_{beam_id}`), HPC 상에서 잡을 쉽게 식별할 수 있도록 한다.
2.  **파일 경로 관리**:
    *   `upload_file`, `download_file` 등의 메서드는 이미 특정 파일과 디렉터리를 다루므로 큰 수정은 필요 없으나, 이들을 호출하는 `FileUploadState`와 `DownloadState`에서 올바른 Beam 단위 경로를 인자로 넘겨주는 것이 중요하다.

## 4. 호출 관계 및 잠재적 문제 (HPC 포함)

### 4.1. 새로운 호출 흐름

1.  **`main.py`**: 신규 Case 폴더 (`/path/to/caseA`) 탐지.
2.  **`ProcessManager`**: `dispatcher_main(case_id='caseA', ...)` 프로세스 생성.
3.  **`dispatcher_main`**: Beam 폴더들 (`beam1`, `beam2`) 탐지 후, 각 Beam에 대한 `worker_main` 프로세스 생성 요청.
4.  **`worker_main` (개별 Beam Worker 내부)**:
    *   `WorkflowManager` (Worker용)가 상태 머신 실행.
    *   **`InitialState` -> `PreprocessingState`**: `mqi_interpreter` 실행하여 해당 Beam 폴더 내에 **다수의 `*.csv` 파일과 개별 `moqui_tps.in` 파일 생성**.
    *   **`FileUploadState`**: `RemoteHandler`를 통해 생성된 **모든 `*.csv` 파일들과 `moqui_tps.in` 파일**을 HPC의 `/remote/path/caseA/beam1/` 폴더로 업로드.
    *   **`HpcExecutionState`**: `RemoteHandler`를 통해 `mqi_simulation` 잡을 HPC에 제출. (입력: `/remote/path/caseA/beam1/`, 잡 이름: `moqui_caseA_beam1`). 반환된 `job_id`를 DB에 업데이트.
    *   **`DownloadState`**: `mqi_simulation`의 결과물인 **단일 `raw` 파일**을 HPC의 `/remote/path/caseA/beam1/` 폴더에서 **`config.yaml`에 지정된 로컬 경로** (예: `C:/mqi/results/caseA/beam1/`)로 다운로드.
    *   **`PostprocessingState` -> `CompletedState`**: 후처리 및 완료.

### 4.2. 잠재적 문제 및 고려사항

*   **GPU 자원 관리 (8개 GPU 총량)**: 전체 시스템에 8개의 GPU가 있으며, 여러 Beam Worker가 동시에 GPU를 요청할 경우 `GpuRepository`에서 경합이 발생할 수 있다. `GpuRepository.assign_free_gpu()` 메서드에 DB 트랜잭션이나 Lock을 적용하여 동시에 같은 GPU를 할당하는 문제를 방지해야 한다. Case당 최대 5개의 Beam이 있으므로, 동시에 처리되는 다중 Case가 있을 경우 GPU 자원 부족이 발생할 수 있어 적절한 큐잉 메커니즘이 필요하다.
*   **HPC 잡 스케줄링 부하**: Case당 최대 5개의 Beam이므로, 동시에 제출되는 잡의 수는 5개로 제한된다. 이는 HPC 스케줄러에 큰 부하를 주지 않을 것으로 예상되므로, '잡 배열(Job Array)' 같은 복잡한 기능은 현 단계에서 고려하지 않아도 된다.
*   **네트워크 부하 및 HPC 파일 관리**: 각 Beam이 개별 `moqui_tps.in` 파일과 최대 50개의 CSV 파일을 가지므로, Worker당 업로드할 파일 수는 적정 수준이다. Case당 최대 5개의 Worker가 동시에 파일을 업로드하더라도 네트워크에 심각한 부하를 줄 가능성은 낮다. **모든 파일을 HPC에 보관하는 정책**에 따라 원격 스토리지 용량 관리가 중요하며, `ProcessManager`의 `max_workers` 수를 적절히 조절하여 네트워크 대역폭을 효율적으로 사용해야 한다.
*   **부분 실패 처리**: 전체 Case 중 일부 Beam만 시뮬레이션에 실패했을 때의 처리 정책이 필요하다. 실패한 Beam만 재시도할 수 있는 메커니즘을 `CaseRepository`와 UI에 구현해야 한다.