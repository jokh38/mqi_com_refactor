Of course. Here is the refactoring guide, rewritten in English based on the final agreed-upon plan.

-----

## **MQI Communicator Refactoring Guide**

### **1. Guide for the AI Assistant**

You are an AI coding assistant tasked with refactoring an existing Python codebase based on this guide (`refactor.md`).

In each work session, you will be provided with **(1) this guide document**, **(2) the original source file for reference**, and **(3) the new Python file skeleton** that you must complete. Your mission is to flesh out the provided skeleton file with detailed comments and complete the code implementation by following the blueprints laid out in **"Section 5. Detailed Implementation Guide."** You must always adhere to the "Global Coding Guidelines."

-----

### **2. Project Overview & Refactoring Goals**

#### **2.1. Overview**

The current `mqi_communicator` project suffers from high complexity and difficult maintenance because some modules handle multiple responsibilities simultaneously. To resolve this, the primary goal is to improve the structure by applying a **Layered Architecture** and the **Separation of Concerns** principle across the entire project.

#### **2.2. Refactoring Goals**

  * **Strengthen the Single Responsibility Principle (SRP):** Restructure the code so that each class and module has only one reason to change.
  * **Enhance Reusability and Scalability:** Make it easier to add or modify features.
  * **Improve Readability and Maintainability:** Organize code into logical units to make it easier to understand and modify.
  * **Reduce Dependencies:** Lower the coupling between modules to enable independent testing and development.

-----

### **3. Final Architecture**

#### **3.1. `src` Directory Structure**

```
src/
├── __init__.py
│
├── core/
│   ├── __init__.py
│   ├── workflow_manager.py
│   └── worker.py
│
├── config/
│   ├── __init__.py
│   ├── settings.py
│   └── constants.py
│
├── database/
│   ├── __init__.py
│   └── connection.py
│
├── domain/
│   ├── __init__.py
│   ├── models.py
│   ├── states.py
│   ├── errors.py
│   └── enums.py
│
├── handlers/
│   ├── __init__.py
│   ├── local_handler.py
│   └── remote_handler.py
│
├── infrastructure/
│   ├── __init__.py
│   ├── gpu_monitor.py
│   ├── logging_handler.py
│   └── process_manager.py
│
├── repositories/
│   ├── __init__.py
│   ├── base.py
│   ├── case_repo.py
│   └── gpu_repo.py
│
├── ui/
│   ├── __init__.py
│   ├── display.py
│   ├── provider.py
│   └── formatter.py
│
└── utils/
    ├── __init__.py
    ├── retry_policy.py
    └── path_manager.py
```

#### **3.2. Package Roles**

  * `core`: Manages the application's core logic (workflow, dependency injection).
  * `config`: Handles configuration loading (`settings.py`) and developer-managed constants (`constants.py`).
  * `database`: Manages low-level database interactions, such as connections and transactions.
  * `domain`: A pure layer defining the application's business rules (states, errors, data models).
  * `handlers`: Processes interactions with external systems, like local/remote command execution.
  * `infrastructure`: Contains low-level functionalities that support the application, such as logging and process management.
  * `repositories`: Responsible for all CRUD operations for specific database tables.
  * `ui`: Manages the terminal dashboard UI, including data fetching, formatting, and rendering.
  * `utils`: Contains reusable, general-purpose utilities (retry policies, path management).

-----

### **4. Global Coding Guidelines**

The following principles must be strictly followed when refactoring all code:

  * **Dependency Injection (DI):** Do not create dependency objects directly within a class. Always inject them from an external source via the constructor (`__init__`).
  * **Externalize Configuration:** All settings, such as file paths and retry counts, must be managed through `config/settings.py`. Do not hardcode these values.
  * **Centralize Constants:** Fixed values managed by the developer (e.g., specific filenames) should be defined in `config/constants.py`.
  * **Use Enums:** For values representing a state, use an `Enum` defined in `domain/enums.py` instead of raw strings.
  * **Rich Error Context:** When an exception is raised, ensure its message includes all context necessary for debugging (e.g., the command that was run, its output, etc.).
  * **Single Responsibility Principle (SRP):** All classes and methods must be designed to have a single, clear responsibility.

-----

### **5. Detailed Implementation Guide**

#### **5.1. Source: `src/database_handler.py`**

Decompose the single `DatabaseHandler` class by separating its responsibilities for DB connection/transaction management and table-specific CRUD operations.

| Old Responsibility | New Location |
| :--- | :--- |
| DB Connection, Transaction, Schema | `src/database/connection.py` |
| `cases` Table CRUD | `src/repositories/case_repo.py` |
| `gpu_resources` Table CRUD | `src/repositories/gpu_repo.py` |
| `nvidia-smi` Result Parsing | `src/infrastructure/gpu_monitor.py` |

\<br\>

##### **👉 Target File \#1: `src/database/connection.py` Blueprint**

  * **Purpose**: To exclusively manage the SQLite database connection, transactions, and schema initialization.
  * **Dependencies**: `db_path: Path`, `config: DatabaseConfig`, `logger: StructuredLogger`
  * **Methods**:
      * `__init__(self, db_path, config, logger)`
      * `transaction(self)`
      * `init_db(self)`
      * `close(self)`
      * **Source**: `__init__`, `transaction`, `init_db`, and `close` methods from `database_handler.py`.

##### **👉 Target File \#2: `src/repositories/case_repo.py` Blueprint**

  * **Purpose**: To manage all CRUD operations for the `cases` table.
  * **Dependencies**: `db_connection: DatabaseConnection`, `logger: StructuredLogger`
  * **Methods**:
      * `__init__(self, db_connection, logger)`
      * `add_case(self, case_id, case_path)`
      * `update_case_status(self, case_id, status, progress)`
      * `get_case(self, case_id)`
      * `get_cases_by_status(self, status)`
      * `record_workflow_step(self, ...)`
      * **Source**: All `cases`-related methods (e.g., `add_case`) from `database_handler.py`.

##### **👉 Target File \#3: `src/repositories/gpu_repo.py` Blueprint**

  * **Purpose**: To manage CRUD for the `gpu_resources` table and handle GPU allocation/deallocation.
  * **Dependencies**: `db_connection: DatabaseConnection`, `logger: StructuredLogger`
  * **Methods**:
      * `__init__(self, db_connection, logger)`
      * `update_resources(self, gpu_data: list)`
          * **Source**: The database update logic from `populate_gpu_resources_from_nvidia_smi` in `database_handler.py`.
      * `assign_gpu_to_case(self, gpu_uuid, case_id)`
      * `release_gpu(self, gpu_uuid)`
      * `find_and_lock_available_gpu(self, case_id)`
      * `get_all_gpu_resources(self)`
      * **Source**: All `gpu_resources`-related methods from `database_handler.py`.

\<br\>

#### **5.2. Source: `src/display_handler.py`**

Decompose the `DisplayHandler` by separating its responsibilities for data fetching, formatting, and UI rendering.

| Old Responsibility | New Location |
| :--- | :--- |
| Fetching & processing data from DB | `src/ui/provider.py` |
| Rendering UI with `rich` library | `src/ui/display.py` |
| Formatting (e.g., color by status) | `src/ui/formatter.py` |

\<br\>

##### **👉 Target File \#1: `src/ui/provider.py` Blueprint**

  * **Purpose**: To fetch and process data required for the UI dashboard from the repositories.
  * **Dependencies**: `case_repo: CaseRepository`, `gpu_repo: GpuRepository`
  * **Methods**:
      * `__init__(self, case_repo, gpu_repo)`
      * `get_system_stats(self)`
      * `get_gpu_data(self)`
      * `get_active_cases_data(self)`
      * **Source**: The data fetching logic from the `_refresh_*` methods in `display_handler.py`.

##### **👉 Target File \#2: `src/ui/formatter.py` Blueprint**

  * **Purpose**: To format data for display (e.g., applying colors based on status).
  * **Methods**: (Primarily pure functions)
      * `format_gpu_status(gpu_status: dict) -> str`
      * `format_case_status(case: dict) -> list`
      * **Source**: Formatting code embedded within the table creation logic of `display_handler.py`.

##### **👉 Target File \#3: `src/ui/display.py` Blueprint**

  * **Purpose**: To exclusively handle rendering the UI with the `rich` library, using data received from the provider.
  * **Dependencies**: `provider: DashboardDataProvider`
  * **Methods**:
      * `__init__(self, provider)`
      * `_create_layout(self)`
      * `update_display(self)`
      * `start(self)` / `stop(self)`
      * **Source**: The `rich`-related UI rendering logic from `display_handler.py`.

\<br\>

#### **5.3. Source: `src/main.py`, `src/worker.py`**

Clarify the responsibilities of the application's entry point and the worker that performs the actual tasks.

| Old Responsibility | New Location |
| :--- | :--- |
| Creating & injecting dependency objects | `src/core/worker.py` |
| Executing workflow & managing state | `src/core/workflow_manager.py` |
| Detecting file system events, managing process pool | `src/main.py` (Remains) |

\<br\>

##### **👉 Target File \#1: `src/core/worker.py` Blueprint**

  * **Purpose**: To act as the "assembly line" that creates all dependency objects for a single case and injects them into the `WorkflowManager` to start the process.
  * **Methods**:
      * `worker_main(case_id, case_path, ...)`
          * **Source**: The existing `worker_main` in `worker.py` and the object initialization logic from `main.py`.
          * **Instructions**: This is where all objects (`DatabaseConnection`, `CaseRepository`, `GpuRepository`, `LocalHandler`, `RemoteHandler`, `WorkflowManager`, etc.) are created. They are then injected into `WorkflowManager`, and `run_workflow()` is called. Must include the 'Fail-Fast' path validation logic.

##### **👉 Target File \#2: `src/core/workflow_manager.py` Blueprint**

  * **Purpose**: To manage and orchestrate the entire workflow for a case according to the State pattern.
  * **Dependencies**: `case_repo: CaseRepository`, `local_handler: LocalHandler`, `remote_handler: RemoteHandler`, etc.
  * **Methods**:
      * `__init__(self, ...)`
      * `run_workflow(self)`
          * **Source**: The core logic from the existing `workflow_manager.py` and `worker.py`.
          * **Instructions**: Responsible for executing each `State` and transitioning to the next, using the injected `repositories` and `handlers`.

(...blueprints for all other files such as `config.py`, `error_categorization.py`, `*_handler.py`, etc., would follow this same format.)