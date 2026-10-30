import numpy as np
import pandas as pd

from battery_ai.analysis import build_cycle_summary, compute_key_metrics
from battery_ai.validation import prepare_battery_data


def _raw_data() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "cyc": [1, 1, 1, 1, 5, 5, 5, 5],
            "step": ["charge", "charge", "discharge", "discharge"] * 2,
            "t": range(8),
            "v": [3.0, 4.0, 4.0, 3.0, 3.0, 4.0, 4.0, 3.0],
            "i": [50, 50, -50, -50] * 2,
            "q": [0, 100, 0, 90, 0, 96, 0, 86.4],
        }
    )


def test_prepare_summary_and_metrics():
    raw = _raw_data()
    mapping = {"cycle": "cyc", "step_type": "step", "time": "t", "voltage": "v", "current": "i", "capacity": "q"}
    prepared = prepare_battery_data(raw, mapping)
    summary = build_cycle_summary(prepared.data)
    metrics = compute_key_metrics(summary, target_cycles=[1, 5], reference_cycle=1)

    assert len(prepared.data) == 8
    assert np.isclose(metrics["first_coulombic_efficiency_pct"], 90.0)
    retentions = metrics["retentions"].set_index("cycle")
    assert np.isclose(retentions.loc[5, "retention_pct"], 96.0)


def test_invalid_and_duplicate_rows_are_reported_and_removed():
    raw = _raw_data()
    raw.loc[1, "v"] = 12.0
    raw = pd.concat([raw, raw.iloc[[0]]], ignore_index=True)
    mapping = {"cycle": "cyc", "step_type": "step", "time": "t", "voltage": "v", "current": "i", "capacity": "q"}
    prepared = prepare_battery_data(raw, mapping, voltage_range=(0, 5))

    report = prepared.quality_report.set_index("检查项")
    assert report.loc["电压超出 [0, 5] V", "数量"] == 1
    assert report.loc["重复记录", "数量"] == 1
    assert prepared.output_rows == 7


def test_current_sign_can_infer_state_without_step_column():
    raw = _raw_data().drop(columns="step")
    mapping = {"cycle": "cyc", "step_type": None, "time": "t", "voltage": "v", "current": "i", "capacity": "q"}
    prepared = prepare_battery_data(raw, mapping)
    assert set(prepared.data["state"]) == {"charge", "discharge"}


def test_duplicates_are_detected_when_time_is_not_mapped():
    raw = _raw_data().drop(columns="t")
    raw = pd.concat([raw, raw.iloc[[0]]], ignore_index=True)
    mapping = {"cycle": "cyc", "step_type": "step", "time": None, "voltage": "v", "current": "i", "capacity": "q"}
    prepared = prepare_battery_data(raw, mapping)
    report = prepared.quality_report.set_index("检查项")
    assert report.loc["重复记录", "数量"] == 1
    assert prepared.output_rows == 8


