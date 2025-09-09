Introduction
============

The MQI Communicator is a Python-based application designed to facilitate communication and data exchange with a remote HPC (High-Performance Computing) system. It provides a robust framework for managing workflows, monitoring system resources, and handling data processing tasks.

Key Features
------------

*   **Remote Workflow Management**: Seamlessly dispatch and monitor jobs on a remote HPC cluster.
*   **Real-time Dashboard**: A terminal-based UI for monitoring the status of jobs, system resources (like GPUs), and overall workflow progress.
*   **Flexible Configuration**: Easily configure the application using YAML files to adapt to different environments and requirements.
*   **Resilient Communication**: Built-in retry policies and error handling to ensure reliable communication with the remote system.
*   **Modular Architecture**: The codebase is organized into distinct layers (core, domain, infrastructure, UI) to promote separation of concerns and maintainability.
