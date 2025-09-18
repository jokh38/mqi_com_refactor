# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Testing
```bash
pytest                    # Run all tests
pytest tests/core/        # Run tests for specific module
pytest -v                 # Run tests with verbose output
```

### Code Quality
```bash
flake8                    # Lint code (max line length: 92 chars)
black .                   # Format code
mypy .                    # Type checking
```

### Building Documentation
```bash
make html                 # Build Sphinx documentation
make clean               # Clean build artifacts
```

### Running the Application
```bash
python main.py           # Start the MQI Communicator application
```

## Architecture Overview

### Core System Purpose
MQI Communicator is a medical physics workflow orchestration system that processes MOQUI SMC (Scattering Monte Carlo) simulation cases. It manages the complete lifecycle from case detection through simulation execution to final output generation.

### Key Architectural Components

#### 1. Main Application Flow (`main.py`)
- Entry point that coordinates filesystem watching, worker process pool management, and application lifecycle
- Uses multiprocessing with ProcessPoolExecutor for concurrent case processing
- Implements watchdog-based filesystem monitoring for new case detection

#### 2. Layered Architecture (`src/`)
- **Domain Layer** (`src/domain/`): Business entities and enums (CaseStatus, BeamStatus, etc.)
- **Core Layer** (`src/core/`): Business logic (WorkflowManager, TpsGenerator, Worker)
- **Infrastructure Layer** (`src/infrastructure/`): External system interfaces (logging, UI, GPU monitoring)
- **Repository Layer** (`src/repositories/`): Data access patterns (CaseRepository, GpuRepository)
- **Handler Layer** (`src/handlers/`): Local and remote execution handlers

#### 3. Configuration System (`src/config/`)
- YAML-based configuration (`config/config.yaml`)
- Structured settings with dataclasses for type safety
- Supports both local and HPC execution environments

#### 4. Database Layer (`src/database/`)
- SQLite database with WAL mode for concurrency
- Repository pattern for data access
- Handles case state persistence and GPU resource tracking

### Workflow Processing Model

The system processes medical physics cases through these phases:
1. **Case Detection**: Filesystem monitoring detects new case directories
2. **Beam Processing**: Each case contains multiple beams processed in parallel workers
3. **TPS Generation**: Creates MOQUI TPS input files for Monte Carlo simulation
4. **Remote Execution**: Submits jobs to HPC cluster via SSH/SLURM
5. **Result Processing**: Downloads and processes simulation outputs
6. **DICOM Generation**: Converts raw outputs to medical imaging format

### Key Design Patterns

#### Worker Process Model
- Each beam is processed by a dedicated worker process (`src/core/worker.py`)
- Workers coordinate through the WorkflowManager which handles state transitions
- Dependency injection pattern used throughout for testability

#### Repository Pattern
- Data access abstracted through repositories (CaseRepository, GpuRepository)
- Enables clean separation between business logic and data persistence

#### Handler Pattern
- LocalHandler and RemoteHandler provide execution environment abstraction
- Enables seamless switching between local testing and HPC production

### Configuration Structure

The main configuration file (`config/config.yaml`) contains:
- **Application settings**: Worker counts, polling intervals, timeouts
- **Path mappings**: Local and remote directory structures with templating
- **HPC connection**: SSH configuration for remote cluster access
- **MOQUI parameters**: Monte Carlo simulation settings
- **Database settings**: SQLite optimization parameters

### Testing Strategy

- Unit tests for each layer with clear separation of concerns
- Test structure mirrors source structure in `tests/` directory
- Pytest configuration in `pytest.ini` with pythonpath set to project root
- Mock objects used extensively for external system dependencies

### External Dependencies

#### Required External Tools
- **mqi_interpreter**: Beam data processing (referenced in config templates)
- **RawToDCM**: DICOM conversion utility (moqui_raw2dicom.py)
- **SLURM**: HPC job scheduling on remote systems
- **nvidia-smi**: GPU monitoring and resource detection

#### Python Dependencies
Key dependencies include watchdog (filesystem monitoring), rich (UI), paramiko (SSH), and PyYAML (configuration).

### Development Notes

- Code formatting follows Black standards with flake8 linting (92 char line limit)
- Type hints used throughout with mypy for static type checking
- Structured logging with JSON format for production monitoring
- All database operations use WAL mode for concurrent access safety