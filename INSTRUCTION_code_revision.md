# Software Development Guidelines

This document outlines best practices and guidelines for developing and maintaining this project, derived from an analysis of its development history. Adhering to these principles will ensure code quality, maintainability, and stability.

## 1. Minimizing the Impact of Changes

To ensure that modifications in one part of the codebase do not unexpectedly affect others, follow these principles:

-   **Use Dependency Injection (DI):** Instead of creating dependencies within a class, inject them via the constructor. This decouples modules, making them easier to test and refactor independently. The `main_controller.py` serves as a central point for assembling and injecting dependencies.
-   **Leverage Centralized Managers:** For cross-cutting concerns like logging, configuration, and SSH connections, use the dedicated manager classes (`Logger`, `ConfigManager`, `SSHConnectionManager`). This centralizes control and ensures that changes to these functionalities only need to be made in one place.
-   **Communicate with Data Transfer Objects (DTOs):** When passing data between modules, group related parameters into a `dataclass` or a simple DTO. This makes function signatures cleaner and more stable. If new data needs to be passed, you can extend the DTO without changing the method signatures, reducing the ripple effect of changes.

## 2. Error Handling and Resilience

To build a robust and reliable system, a proactive approach to error handling is essential:

-   **Implement Multi-Level Retries:** For operations prone to transient failures, such as network requests, implement a retry mechanism with **exponential backoff**. This prevents the system from failing due to temporary issues.
-   **Log Detailed Error Context:** When an error occurs, log all relevant context, including input parameters, state variables, and full error messages (e.g., `stdout`, `stderr`, `exit_code` from remote commands). This is crucial for diagnosing and debugging issues quickly.
-   **Ensure Resource Cleanup and Self-Healing:** Implement mechanisms to detect and recover from inconsistent states, especially after a crash or unexpected shutdown. This includes cleaning up stale lock files, terminating orphaned remote processes, and resetting job statuses to a clean state upon startup.

## 3. Code Refactoring Principles

Continuous improvement of the codebase is key to long-term maintainability.

-   **Enforce the Single Responsibility Principle (SRP):** Each class and method should have one, and only one, reason to change. If a class becomes too large or handles multiple concerns, refactor it by splitting it into smaller, more focused modules.
-   **Externalize All Configuration:** Avoid hardcoding values like file paths, retry counts, or feature flags. Move them to the central `config.json` file. This allows for flexible configuration without requiring code changes.
-   **Centralize State Management:** Avoid scattering state across multiple files or objects. Consolidate status tracking into a "single source of truth" (e.g., the central `case_status.json`). This prevents data inconsistencies and simplifies state management.
-   **Favor Iteration Over Deep Recursion:** While recursion can be elegant, it can also lead to `StackOverflow` errors with large datasets. Prefer iterative approaches using loops and state machines, which are generally safer and easier to debug.

## 4. AI Code Assistant Prompting Guide

To maximize efficiency and leverage AI assistants effectively while minimizing context window usage, follow these prompt strategies:

-   **Provide Clear Goals and Roles:** Frame requests with specific, architecture-aware goals. Instead of "Fix this code," try: "Refactor `MyClass` to use the central `ConfigManager` for configuration instead of reading `config.json` directly. Inject it as a dependency in the constructor."
-   **Supply Minimal, Targeted Context:** Provide only the essential code snippets required for the task. For a refactoring task, this might include the class to be changed and the relevant parts of its instantiator, but not the entire application.
-   **Use Planning Documents (Manifestos):** For complex features, first write a brief markdown document outlining the plan. Then, provide this "manifesto" to the AI and ask it to implement the code according to the plan. This ensures consistency over multiple interactions.
-   **Delegate Documentation and Commit Messages:** After making changes, provide the `git diff` output to the AI and ask it to generate a detailed commit message that follows the project's established format. For example: "Based on the following `git diff`, write a commit message in the project's style (`[TAG] Summary`). Describe the problem, the solution, and the benefits, and include a bulleted list of key changes."
