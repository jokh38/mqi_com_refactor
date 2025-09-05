# =====================================================================================
# Target File: src/ui/provider.py
# Source Reference: src/display_handler.py
# =====================================================================================

from typing import Dict, List, Any, Optional
from datetime import datetime

from src.repositories.case_repo import CaseRepository
from src.repositories.gpu_repo import GpuRepository
from src.infrastructure.logging_handler import StructuredLogger
from src.domain.models import CaseData, GpuResource
from src.domain.enums import CaseStatus, GpuStatus


class DashboardDataProvider:
    """
    Fetches and processes data required for the UI dashboard from the repositories.
    
    FROM: Extracts data fetching logic from the `_refresh_*` methods in `display_handler.py`.
    RESPONSIBILITY: Pure data fetching and processing without any UI rendering logic.
    """

    def __init__(self, case_repo: CaseRepository, gpu_repo: GpuRepository, logger: StructuredLogger):
        """
        Initializes the provider with injected repositories.
        """
        self.case_repo = case_repo
        self.gpu_repo = gpu_repo
        self.logger = logger
        self._last_update: Optional[datetime] = None
        self._system_stats: Dict[str, Any] = {}
        self._gpu_data: List[Dict[str, Any]] = []
        self._active_cases: List[Dict[str, Any]] = []

    def get_system_stats(self) -> Dict[str, Any]:
        """
        Returns the latest system-level statistics.
        """
        return self._system_stats

    def get_gpu_data(self) -> List[Dict[str, Any]]:
        """
        Returns the latest GPU resource data.
        """
        return self._gpu_data

    def get_active_cases_data(self) -> List[Dict[str, Any]]:
        """
        Returns the latest data for active cases.
        """
        return self._active_cases

    def refresh_all_data(self) -> None:
        """
        Triggers a refresh of all data by fetching from repositories and processing it.
        """
        try:
            self.logger.info("Refreshing all dashboard data")

            # Fetch raw data
            raw_gpus = self.gpu_repo.get_all_gpu_resources()
            raw_cases = self.case_repo.get_all_active_cases()

            # Process data
            self._gpu_data = self._process_gpu_data(raw_gpus)
            self._active_cases = self._process_case_data(raw_cases)
            self._system_stats = self._calculate_system_metrics(raw_cases, raw_gpus)

            self._last_update = datetime.now()

        except Exception as e:
            self.logger.error("Failed to refresh dashboard data", {"error": str(e)})
            # In case of error, clear data to avoid displaying stale info
            self._system_stats = {}
            self._gpu_data = []
            self._active_cases = []


    def _calculate_system_metrics(self, cases: List[CaseData], gpus: List[GpuResource]) -> Dict[str, Any]:
        """
        Calculates derived system metrics from raw repository data.
        """
        total_gpus = len(gpus)
        available_gpus = sum(1 for gpu in gpus if gpu.status == GpuStatus.IDLE)
        
        # Initialize all possible statuses to ensure they exist in the dictionary
        status_counts = {status: 0 for status in CaseStatus}

        for case in cases:
            if case.status in status_counts:
                status_counts[case.status] += 1
            
        return {
            "total_cases": len(cases),
            "pending": status_counts.get(CaseStatus.PENDING, 0),
            "preprocessing": status_counts.get(CaseStatus.PREPROCESSING, 0),
            "processing": status_counts.get(CaseStatus.PROCESSING, 0),
            "postprocessing": status_counts.get(CaseStatus.POSTPROCESSING, 0),
            "total_gpus": total_gpus,
            "available_gpus": available_gpus,
            "last_update": self._last_update
        }

    def _process_case_data(self, raw_cases: List[CaseData]) -> List[Dict[str, Any]]:
        """
        Processes raw case data into a format suitable for display.
        """
        processed_cases = []
        for case in raw_cases:
            processed_cases.append({
                "case_id": case.case_id,
                "status": case.status,
                "progress": case.progress,
                "assigned_gpu": case.assigned_gpu,
                "elapsed_time": (datetime.now() - case.created_at).total_seconds() if case.created_at else 0
            })
        return processed_cases

    def _process_gpu_data(self, raw_gpu_data: List[GpuResource]) -> List[Dict[str, Any]]:
        """
        Processes raw GPU data into a format suitable for display.
        """
        processed_gpus = []
        for gpu in raw_gpu_data:
            processed_gpus.append({
                "uuid": gpu.uuid,
                "name": gpu.name,
                "status": gpu.status,
                "assigned_case": gpu.assigned_case,
                "memory_used": gpu.memory_used,
                "memory_total": gpu.memory_total,
                "utilization": gpu.utilization,
                "temperature": gpu.temperature
            })
        return processed_gpus