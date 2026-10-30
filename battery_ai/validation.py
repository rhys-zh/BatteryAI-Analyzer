"""Canonicalisation, validation, and transparent row-cleaning rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pandas as pd


REQUIRED_FIELDS = ("cycle", "voltage", "current", "capacity")


@dataclass(frozen=True)
class PreparationResult:
    data: pd.DataFrame
    quality_report: pd.DataFrame
    input_rows: int
    output_rows: int


def validate_mapping(mapping: Mapping[str, str | None], columns: list[str]) -> None:
    missing = [field for field in REQUIRED_FIELDS if not mapping.get(field)]
    if missing:
        labels = {
            "cycle": "循环序号",
            "voltage": "电压",
            "current": "电流",
            "capacity": "容量",
        }
        raise ValueError("请完成必填列映射：" + "、".join(labels[item] for item in missing))
    unknown = [value for value in mapping.values() if value and value not in columns]
    if unknown:
        raise ValueError("映射列不存在：" + "、".join(map(str, unknown)))


def _parse_time_to_seconds(series: pd.Series, unit: str) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    numeric_ratio = float(numeric.notna().mean()) if len(series) else 0.0
    if numeric_ratio >= 0.8:
        multiplier = {"s": 1.0, "min": 60.0, "h": 3600.0}[unit]
        return numeric * multiplier
    parsed = pd.to_timedelta(series.astype(str), errors="coerce")
    return parsed.dt.total_seconds()


def _normalise_step_type(series: pd.Series) -> pd.Series:
    def normalise(value: object) -> str:
        text = str(value).strip().casefold()
        if any(token in text for token in ("discharge", "dchg", "放电")):
            return "discharge"
        if any(token in text for token in ("charge", "chg", "充电")):
            return "charge"
        return "unknown"

    return series.map(normalise)


def prepare_battery_data(
    raw: pd.DataFrame,
    mapping: Mapping[str, str | None],
    *,
    capacity_unit: str = "mAh",
    current_unit: str = "mA",
    time_unit: str = "s",
    positive_current_is_charge: bool = True,
    voltage_range: tuple[float, float] = (0.0, 5.0),
    remove_duplicates: bool = True,
) -> PreparationResult:
    """Map raw columns and apply explicit, auditable cleaning rules."""

    validate_mapping(mapping, list(raw.columns))
    canonical = pd.DataFrame(index=raw.index)
    canonical["source_row"] = np.arange(2, len(raw) + 2)
    canonical["cycle"] = pd.to_numeric(raw[mapping["cycle"]], errors="coerce")
    canonical["voltage_v"] = pd.to_numeric(raw[mapping["voltage"]], errors="coerce")
    canonical["current"] = pd.to_numeric(raw[mapping["current"]], errors="coerce")
    canonical["capacity"] = pd.to_numeric(raw[mapping["capacity"]], errors="coerce")

    if mapping.get("time"):
        canonical["time_s"] = _parse_time_to_seconds(raw[mapping["time"]], time_unit)
    else:
        canonical["time_s"] = np.arange(len(raw), dtype=float)

    current_multiplier = {"mA": 1.0, "A": 1000.0}[current_unit]
    capacity_multiplier = {"mAh": 1.0, "Ah": 1000.0}[capacity_unit]
    canonical["current_ma"] = canonical.pop("current") * current_multiplier
    canonical["capacity_mah"] = canonical.pop("capacity").abs() * capacity_multiplier

    if mapping.get("step_type"):
        canonical["state"] = _normalise_step_type(raw[mapping["step_type"]])
    else:
        canonical["state"] = "unknown"

    positive_state = "charge" if positive_current_is_charge else "discharge"
    negative_state = "discharge" if positive_current_is_charge else "charge"
    infer_mask = canonical["state"].eq("unknown")
    canonical.loc[infer_mask & canonical["current_ma"].gt(0), "state"] = positive_state
    canonical.loc[infer_mask & canonical["current_ma"].lt(0), "state"] = negative_state

    issues: list[dict[str, object]] = []

    invalid_numeric = canonical[list(("cycle", "voltage_v", "current_ma", "capacity_mah"))].isna().any(axis=1)
    issues.append(
        {
            "检查项": "必需数值缺失或无法解析",
            "数量": int(invalid_numeric.sum()),
            "处理": "剔除",
        }
    )

    invalid_cycle = canonical["cycle"].notna() & canonical["cycle"].lt(1)
    issues.append({"检查项": "循环序号 < 1", "数量": int(invalid_cycle.sum()), "处理": "剔除"})

    voltage_low, voltage_high = voltage_range
    invalid_voltage = canonical["voltage_v"].notna() & ~canonical["voltage_v"].between(
        voltage_low, voltage_high, inclusive="both"
    )
    issues.append(
        {
            "检查项": f"电压超出 [{voltage_low:g}, {voltage_high:g}] V",
            "数量": int(invalid_voltage.sum()),
            "处理": "剔除",
        }
    )

    unknown_state = canonical["state"].eq("unknown")
    issues.append(
        {
            "检查项": "无法判断充/放电状态",
            "数量": int(unknown_state.sum()),
            "处理": "保留，但不参与曲线与循环汇总",
        }
    )

    clean = canonical.loc[~(invalid_numeric | invalid_cycle | invalid_voltage)].copy()
    duplicate_columns = ["cycle", "voltage_v", "current_ma", "capacity_mah", "state"]
    if mapping.get("time"):
        duplicate_columns.insert(1, "time_s")
    duplicate_mask = clean.duplicated(subset=duplicate_columns, keep="first")
    duplicate_count = int(duplicate_mask.sum())
    if remove_duplicates:
        clean = clean.loc[~duplicate_mask].copy()
        duplicate_action = "剔除"
    else:
        duplicate_action = "保留"
    issues.append({"检查项": "重复记录", "数量": duplicate_count, "处理": duplicate_action})

    clean["cycle"] = clean["cycle"].round().astype(int)
    clean = clean.sort_values(["cycle", "time_s", "source_row"]).reset_index(drop=True)
    report = pd.DataFrame(issues)
    return PreparationResult(
        data=clean,
        quality_report=report,
        input_rows=len(raw),
        output_rows=len(clean),
    )

