"""Deterministic cycle-level summaries and battery metrics."""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd


def build_cycle_summary(data: pd.DataFrame) -> pd.DataFrame:
    """Summarise max step capacity and mean voltage for each cycle/state."""

    active = data[data["state"].isin(["charge", "discharge"])].copy()
    if active.empty:
        return pd.DataFrame(
            columns=[
                "cycle",
                "charge_capacity_mah",
                "discharge_capacity_mah",
                "coulombic_efficiency_pct",
                "avg_charge_voltage_v",
                "avg_discharge_voltage_v",
            ]
        )

    capacities = active.pivot_table(
        index="cycle",
        columns="state",
        values="capacity_mah",
        aggfunc="max",
    ).rename(
        columns={
            "charge": "charge_capacity_mah",
            "discharge": "discharge_capacity_mah",
        }
    )
    voltages = active.pivot_table(
        index="cycle",
        columns="state",
        values="voltage_v",
        aggfunc="mean",
    ).rename(
        columns={
            "charge": "avg_charge_voltage_v",
            "discharge": "avg_discharge_voltage_v",
        }
    )
    summary = capacities.join(voltages, how="outer").reset_index()
    for column in (
        "charge_capacity_mah",
        "discharge_capacity_mah",
        "avg_charge_voltage_v",
        "avg_discharge_voltage_v",
    ):
        if column not in summary:
            summary[column] = np.nan
    valid_charge = summary["charge_capacity_mah"].replace(0, np.nan)
    summary["coulombic_efficiency_pct"] = (
        summary["discharge_capacity_mah"] / valid_charge * 100.0
    )
    return summary.sort_values("cycle").reset_index(drop=True)


def compute_key_metrics(
    summary: pd.DataFrame,
    target_cycles: Iterable[int] = (1, 5, 10, 20, 50),
    reference_cycle: int | None = 1,
) -> dict[str, object]:
    """Calculate first valid efficiency and target-cycle capacity retention."""

    valid_efficiency = summary.dropna(
        subset=["charge_capacity_mah", "discharge_capacity_mah", "coulombic_efficiency_pct"]
    )
    first_efficiency = (
        float(valid_efficiency.iloc[0]["coulombic_efficiency_pct"])
        if not valid_efficiency.empty
        else np.nan
    )
    first_efficiency_cycle = (
        int(valid_efficiency.iloc[0]["cycle"]) if not valid_efficiency.empty else None
    )

    discharge = summary.dropna(subset=["discharge_capacity_mah"])
    selected_reference = discharge[discharge["cycle"].eq(reference_cycle)]
    if selected_reference.empty and not discharge.empty:
        selected_reference = discharge.iloc[[0]]
    baseline_capacity = (
        float(selected_reference.iloc[0]["discharge_capacity_mah"])
        if not selected_reference.empty
        else np.nan
    )
    baseline_cycle = int(selected_reference.iloc[0]["cycle"]) if not selected_reference.empty else None

    retentions: list[dict[str, float | int | None]] = []
    for cycle in target_cycles:
        row = summary[summary["cycle"].eq(int(cycle))]
        capacity = float(row.iloc[0]["discharge_capacity_mah"]) if not row.empty else np.nan
        retention = (
            capacity / baseline_capacity * 100.0
            if np.isfinite(capacity) and np.isfinite(baseline_capacity) and baseline_capacity != 0
            else np.nan
        )
        retentions.append(
            {
                "cycle": int(cycle),
                "discharge_capacity_mah": capacity,
                "retention_pct": retention,
            }
        )

    return {
        "first_coulombic_efficiency_pct": first_efficiency,
        "first_efficiency_cycle": first_efficiency_cycle,
        "reference_cycle": baseline_cycle,
        "reference_discharge_capacity_mah": baseline_capacity,
        "retentions": pd.DataFrame(retentions),
    }

