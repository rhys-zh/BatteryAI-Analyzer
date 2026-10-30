import numpy as np
import pandas as pd
import pytest

from battery_ai.anomaly import AnomalyDetectionError, detect_cycle_anomalies


def _summary(n_cycles: int = 20) -> pd.DataFrame:
    cycle = np.arange(1, n_cycles + 1)
    discharge = 100 - cycle * 0.1
    discharge[-1] = 70
    return pd.DataFrame(
        {
            "cycle": cycle,
            "charge_capacity_mah": 101 - cycle * 0.1,
            "discharge_capacity_mah": discharge,
            "coulombic_efficiency_pct": discharge / (101 - cycle * 0.1) * 100,
            "avg_charge_voltage_v": 3.5 + cycle * 0.0001,
            "avg_discharge_voltage_v": 3.4 - cycle * 0.0001,
        }
    )


def test_anomaly_detection_returns_score_reason_and_metadata():
    result, metadata = detect_cycle_anomalies(_summary(), contamination=0.1)
    assert len(result) == 20
    assert {"anomaly_score", "is_anomaly", "reason"}.issubset(result.columns)
    assert metadata["threshold"] == 0.0
    assert result["is_anomaly"].sum() >= 1
    assert bool(result.loc[result["cycle"].eq(20), "is_anomaly"].iloc[0])


def test_too_few_cycles_are_rejected():
    with pytest.raises(AnomalyDetectionError, match="至少需要 8"):
        detect_cycle_anomalies(_summary(7))

