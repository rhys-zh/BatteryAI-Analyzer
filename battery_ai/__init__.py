"""Core analysis package for BatteryAI-Analyzer."""

from .analysis import build_cycle_summary, compute_key_metrics
from .anomaly import AnomalyDetectionError, detect_cycle_anomalies
from .data_loader import auto_detect_mapping, read_table_bytes
from .validation import prepare_battery_data

__all__ = [
    "AnomalyDetectionError",
    "auto_detect_mapping",
    "build_cycle_summary",
    "compute_key_metrics",
    "detect_cycle_anomalies",
    "prepare_battery_data",
    "read_table_bytes",
]

