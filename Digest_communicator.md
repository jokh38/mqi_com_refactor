This document provides a comprehensive overview of the MQI Communicator application, generated from the docstrings within its Python source code.

## MQI Communicator Application Documentation

### 1. Main Application (`main.py`)

The main entry point for the MQI Communicator application. This script is responsible for:
- Watching for new case directories.
- Managing a worker process pool to handle case processing.
- Coordinating the application startup and shutdown.
- Handling top-level error recovery.

The `MQIApplication` class is the main controller, managing the lifecycle including initialization, coordination of components, and graceful shutdown.

**Key Functions in `main.py`:**

-   `scan_existing_cases`: Scans for existing cases at startup by comparing file system cases with database records and queuing new cases.
-   `CaseDetectionHandler`: A `FileSystemEventHandler` that handles file system events to detect new case directories and queues them for processing.
-   `MQIApplication`: The main application controller.
    -   `initialize_logging`: Initializes structured logging.
    -   `initialize_database`: Initializes the database connection and schema.
    -   `start_file_watcher`: Starts the file system watcher to detect new cases.
    -   `start_dashboard`: Starts the dashboard UI in a separate process.
    -   `start_gpu_monitor`: Starts the GPU monitoring service.
    -   `run_worker_loop`: The main loop for processing cases from the queue, managing a process pool to handle cases concurrently.
    -   `_monitor_services`: Periodically monitors the health of critical background services.
    -   `shutdown`: Performs a graceful shutdown of all application components.
    -   `run`: The main entry point for running the application.
-   `setup_signal_handlers`: Sets up signal handlers for graceful application shutdown.
-   `main`: The main entry point of the application, parsing command-line arguments and running the `MQIApplication`.

### 2. Configuration (`src/config/`)

#### `constants.py`

Defines developer-managed constants for the application. These are fixed values not meant for user configuration, representing hardcoded application behavior and data structures. This includes database schema constants, file system constants, command templates, workflow state names, validation constants, error message templates, UI display constants, system resource limits, and MOQUI TPS parameter names.

#### `settings.py`

Manages application configuration settings. It defines the configuration structure using dataclasses and provides a `Settings` class to load configuration from environment variables and a YAML file.

**Configuration Dataclasses:**

-   `DatabaseConfig`: For database settings.
-   `ProcessingConfig`: For processing settings.
-   `GpuConfig`: For GPU resource management.
-   `LoggingConfig`: For logging settings.
-   `UIConfig`: For UI display settings.
-   `HandlerConfig`: For local and remote command handlers.
-   `RetryPolicyConfig`: For retry policy settings.

**`Settings` Class:**
The main configuration class that loads and manages all settings from environment variables and a YAML file.

### 3. Core Logic (`src/core/`)

#### `case_aggregator.py`

Contains logic for aggregating beam statuses to update the overall case status. The `update_case_status_from_beams` function checks the status of all beams for a given case and updates the parent case's status accordingly (e.g., if all beams are completed, the case is completed).

#### `dispatcher.py`

Contains logic for dispatching cases and beams for processing.

-   `run_case_level_csv_interpreting`: Runs the `mqi_interpreter` for the entire case to generate CSV files.
-   `run_case_level_upload`: Uploads all generated CSV files to each beam's remote directory.
-   `prepare_beam_jobs`: Scans a case directory for beams and returns a list of jobs to be processed by workers.

#### `tps_generator.py`

Contains the `TpsGenerator` service for creating `moqui_tps.in` files. This service generates dynamic, case-specific configuration files at runtime based on parameters from `config.yaml` and dynamic case data like GPU allocation and file paths.

#### `worker.py`

The main entry point for a worker process that handles a single beam. The `worker_main` function acts as an "assembly line" that creates all dependency objects for a single beam and injects them into the `WorkflowManager` to start the process.

#### `workflow_manager.py`

Manages and orchestrates the entire workflow for a case using a state pattern. The `WorkflowManager` class is responsible for executing each state and transitioning to the next, using injected repositories and handlers.

### 4. Database (`src/database/`)

#### `connection.py`

Manages SQLite database connections, transactions, and schema initialization. The `DatabaseConnection` class handles connection management and schema initialization, providing thread-safe transaction handling.

### 5. Domain Model (`src/domain/`)

#### `enums.py`

Defines enumerations for statuses and modes used throughout the application, including `CaseStatus`, `BeamStatus`, `WorkflowStep`, `GpuStatus`, and `ProcessingMode`.

#### `errors.py`

Defines custom exception classes for the application, such as `DatabaseError`, `GpuResourceError`, `WorkflowError`, `ConfigurationError`, `ProcessingError`, `ValidationError`, `RetryableError`, and `CircuitBreakerOpenError`.

#### `models.py`

Defines Data Transfer Objects (DTOs) for the application's domain models: `CaseData`, `BeamData`, `GpuResource`, `WorkflowStepRecord`, and `SystemStats`.

#### `states.py`

Defines the state machine for the workflow using the State pattern. It includes an abstract base class `WorkflowState` and concrete state implementations for each step of the process, such as `InitialState`, `FileUploadState`, `HpcExecutionState`, `DownloadState`, `PostprocessingState`, `CompletedState`, and `FailedState`.

### 6. Handlers (`src/handlers/`)

#### `local_handler.py`

Handles the execution of local command-line interface (CLI) tools. The `LocalHandler` class uses injected dependencies (`CommandExecutor`, `RetryPolicy`) to execute commands with a retry policy. It provides methods to run tools like `mqi_interpreter` and `raw_to_dcm`.

#### `remote_handler.py`

Manages HPC communication, remote execution, and file transfers. The `RemoteHandler` class handles SSH/SFTP connections, remote command execution, and file transfers, with improved error handling and connection management.

### 7. Infrastructure (`src/infrastructure/`)

#### `gpu_monitor.py`

A long-running service that periodically fetches GPU resource data from a remote host and updates a local repository. The `GpuMonitor` class separates data acquisition and parsing from data persistence.

#### `logging_handler.py`

Provides structured logging capabilities and a logger factory. The `StructuredLogger` class offers structured logging with JSON formatting and context management.

#### `process_manager.py`

Manages process pools and subprocess execution for the application. The `ProcessManager` class handles the worker pool, while the `CommandExecutor` handles subprocess command execution with error handling and logging.

#### `ui_process_manager.py`

Manages the UI subprocess lifecycle, handling its creation, monitoring, and termination. The `UIProcessManager` is responsible for launching and managing the UI as a separate process, with proper console window handling on Windows systems.

### 8. Repositories (`src/repositories/`)

#### `base.py`

Contains the abstract base class `BaseRepository` for all repository implementations, providing common database access patterns and error handling.

#### `case_repo.py`

Manages all CRUD operations for the 'cases' and related tables. The `CaseRepository` class implements the Repository Pattern for case and beam data access.

#### `gpu_repo.py`

Manages all CRUD operations for the 'gpu_resources' table and handles GPU allocation/deallocation. This class separates GPU data persistence from `nvidia-smi` parsing.

### 9. User Interface (`src/ui/`)

#### `dashboard.py`

The UI Process Entry Point for the MQI Communicator Dashboard. This script initializes all necessary components and starts the display manager in its own process space.

#### `formatter.py`

Contains helper functions for formatting data for the UI, providing color-coded and formatted text for statuses, memory usage, utilization, temperature, and progress bars.

#### `provider.py`

Fetches and processes data required for the UI dashboard from the repositories. The `DashboardDataProvider` is responsible for pure data fetching and processing without any UI rendering logic.

### 10. Utilities (`src/utils/`)

#### `path_manager.py`

Manages file system paths and operations in a centralized, reusable way. The `PathManager` class provides methods for path validation, directory creation, temporary file handling, and other file system operations.

#### `retry_policy.py`

Provides a configurable retry policy and a circuit breaker pattern. The `RetryPolicy` class offers a reusable, configurable retry mechanism with different strategies, while the `CircuitBreaker` class implements the Circuit Breaker pattern for handling cascading failures.