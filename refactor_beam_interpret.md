# Refactoring Plan: Individual Beam Interpretation

## 1. Goal

To modify the preprocessing workflow to correctly interpret each individual "beam" subdirectory within a case folder, rather than attempting to process the entire case folder at once. The `mqi_interpreter` should be executed once for every beam subdirectory.

---

## 2. Analysis of Current Implementation

The current implementation is incorrect because the `PreprocessingState` in `src/domain/states.py` invokes the `mqi_interpreter` only once, passing the top-level `case_path` as the primary argument. The logic in `src/handlers/local_handler.py` confirms this, as it constructs a single command:

```python
# From local_handler.py
command = [self.python_interpreter, mqi_interpreter_path, str(case_path)]
```

This approach fails to iterate over the individual beam subdirectories, which is the required behavior.

---

## 3. Proposed Refactoring Plan

The core business logic for the workflow resides in the state machine. Therefore, the change should be implemented in `PreprocessingState`, leaving the `LocalHandler` as a generic command executor.

### **Target File:** `src/domain/states.py`

### **Target State:** `PreprocessingState`

The `execute` method of this class will be completely overhauled.

#### **New Step-by-Step Logic:**

1.  **Identify Beam Subdirectories:**
    -   Inside the `execute` method, get the top-level `case_path` from the workflow context.
    -   Scan this `case_path` to find all immediate subdirectories. These are assumed to be the "beam" directories.
    -   A list of these directories should be compiled (e.g., `beam_paths = [d for d in context.case_path.iterdir() if d.is_dir()]`).

2.  **Add Pre-computation Checks:**
    -   If no beam subdirectories are found, this is an error condition. The workflow should log this error and transition to `FailedState`.

3.  **Iterate and Execute:**
    -   Loop through the `beam_paths` list.
    -   Inside the loop, for each `beam_path`:
        -   Log the start of the interpretation for the specific beam (e.g., `f"Interpreting beam: {beam_path.name}"`).
        -   Invoke the `mqi_interpreter` by calling `context.local_handler.run_mqi_interpreter`.
        -   **Crucially, the `case_path` argument for this call must be the current `beam_path` from the iteration.**
        -   The `input_file` argument should still point to the `moqui_tps.in` file located in the parent case directory (`context.case_path`).
        -   The `output_dir` argument should point to the single, shared processing directory for the entire case.

4.  **Implement Robust Error Handling:**
    -   Inside the loop, check the `ExecutionResult` from each `run_mqi_interpreter` call.
    -   If any single beam interpretation fails (`result.success is False`), the loop must be terminated immediately.
    -   The failure details (error message, beam path) should be logged, and the workflow must transition to `FailedState`.

5.  **Verify Collective Success:**
    -   After the loop completes without any failures, perform a final check to ensure that at least one CSV file was generated in the `processing_directory`.
    -   If no CSV files are found, log an error and transition to `FailedState`.
    -   If CSV files exist, the state has completed successfully. Log the total number of beams processed and transition to `FileUploadState`.

---

## 4. Impact on Other Components

-   **`src/handlers/local_handler.py`**: **No changes required.** The `run_mqi_interpreter` method is already generic enough to accept a path and execute the interpreter. By modifying the *caller* (`PreprocessingState`), we preserve the handler's role as a simple execution layer.
-   **`config/config.yaml`**: **No changes required.** The paths and executables are configured correctly.
