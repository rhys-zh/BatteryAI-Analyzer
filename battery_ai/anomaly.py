"""Exploratory Isolation Forest analysis with inspectable diagnostics."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler


FEATURE_LABELS = {
    "charge_capacity_mah": "充电容量",
    "discharge_capacity_mah": "放电容量",
    "coulombic_efficiency_pct": "库伦效率",
    "avg_charge_voltage_v": "平均充电电压",
    "avg_discharge_voltage_v": "平均放电电压",
}


class AnomalyDetectionError(ValueError):
    """Raised when the data cannot support a meaningful exploratory model."""


def _robust_deviation(series: pd.Series) -> pd.Series:
    median = float(series.median())
    mad = float((series - median).abs().median())
    if mad > 1e-12:
        return 0.6745 * (series - median) / mad
    std = float(series.std(ddof=0))
    if std > 1e-12:
        return (series - median) / std
    return pd.Series(0.0, index=series.index)


def detect_cycle_anomalies(
    summary: pd.DataFrame,
    *,
    contamination: float = 0.1,
    random_state: int = 42,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Fit Isolation Forest and return per-cycle scores plus human-readable clues."""

    if not 0.01 <= contamination <= 0.4:
        raise AnomalyDetectionError("预期异常比例必须在 0.01 到 0.40 之间。")

    candidate_features = [column for column in FEATURE_LABELS if column in summary]
    features = [
        column
        for column in candidate_features
        if summary[column].notna().sum() >= 3 and summary[column].nunique(dropna=True) > 1
    ]
    usable = summary.dropna(subset=["cycle"]).copy()
    if len(usable) < 8:
        raise AnomalyDetectionError("至少需要 8 个有效循环，才能运行探索性异常检测。")
    if len(features) < 2:
        raise AnomalyDetectionError("至少需要 2 个有变化的循环级特征。")

    matrix = usable[features].copy()
    medians = matrix.median(numeric_only=True)
    matrix = matrix.fillna(medians)
    scaled = StandardScaler().fit_transform(matrix)
    model = IsolationForest(
        n_estimators=300,
        contamination=contamination,
        random_state=random_state,
        n_jobs=-1,
    )
    predictions = model.fit_predict(scaled)
    decision_scores = model.decision_function(scaled)

    deviations = pd.DataFrame(
        {column: _robust_deviation(matrix[column]) for column in features},
        index=matrix.index,
    )

    def explain(row_index: int, is_anomaly: bool) -> str:
        row = deviations.loc[row_index]
        ranked = row.abs().sort_values(ascending=False)
        clues: list[str] = []
        for feature in ranked.index[:2]:
            value = float(row[feature])
            if abs(value) < 1.0:
                continue
            direction = "高于" if value > 0 else "低于"
            clues.append(f"{FEATURE_LABELS[feature]}{direction}中位水平（稳健偏差 {abs(value):.1f}）")
        if clues:
            return "；".join(clues)
        if is_anomaly:
            return "多特征组合较孤立；单项稳健偏差均不突出"
        return "未见明显单项偏离"

    result = usable[["cycle", *features]].copy()
    result["anomaly_score"] = decision_scores
    result["is_anomaly"] = predictions == -1
    result["reason"] = [
        explain(index, bool(flag))
        for index, flag in zip(result.index, result["is_anomaly"])
    ]
    result = result.sort_values("anomaly_score").reset_index(drop=True)
    metadata = {
        "features": features,
        "feature_labels": [FEATURE_LABELS[column] for column in features],
        "threshold": 0.0,
        "contamination": contamination,
        "expected_anomalies": max(1, math.ceil(len(result) * contamination)),
        "n_cycles": len(result),
        "random_state": random_state,
    }
    return result, metadata

