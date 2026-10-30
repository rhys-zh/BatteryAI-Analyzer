"""Robust CSV/Excel loading and column-name suggestions for battery data."""

from __future__ import annotations

from io import BytesIO, StringIO
from pathlib import Path
import re
from typing import Iterable

import pandas as pd


COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "cycle": (
        "cycle index",
        "cycle id",
        "cycle no",
        "cycle",
        "循环序号",
        "循环编号",
        "循环号",
        "循环",
    ),
    "step_type": (
        "step type",
        "step name",
        "step status",
        "status",
        "工步类型",
        "工步名称",
        "工步状态",
        "状态",
    ),
    "time": (
        "total time",
        "test time",
        "record time",
        "step time",
        "relative time",
        "总时间",
        "测试时间",
        "记录时间",
        "工步时间",
        "时间",
    ),
    "voltage": ("voltage(v)", "voltage", "电压(v)", "电压"),
    "current": (
        "current(ma)",
        "current(a)",
        "current",
        "电流(ma)",
        "电流(a)",
        "电流",
    ),
    "capacity": (
        "capacity(mah)",
        "capacity(ah)",
        "capacity",
        "specific capacity",
        "容量(mah)",
        "容量(ah)",
        "容量",
        "比容量",
    ),
}


def _normalise_name(value: object) -> str:
    text = str(value).strip().casefold()
    return re.sub(r"[\s_\-\[\]（）()]+", "", text)


def _alias_score(values: Iterable[object]) -> int:
    aliases = {
        _normalise_name(alias)
        for names in COLUMN_ALIASES.values()
        for alias in names
    }
    score = 0
    for value in values:
        normalised = _normalise_name(value)
        if any(alias == normalised or alias in normalised for alias in aliases):
            score += 1
    return score


def _detect_text_header_row(text: str, max_rows: int = 30) -> int:
    """Find a probable header row in a CSV that may contain a Neware preamble."""

    best_row, best_score = 0, 0
    for row_number, line in enumerate(text.splitlines()[:max_rows]):
        values = re.split(r"[,;\t]", line)
        score = _alias_score(values)
        if score > best_score:
            best_row, best_score = row_number, score
    return best_row if best_score >= 2 else 0


def _decode_csv(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("无法识别 CSV 编码（已尝试 UTF-8、GB18030 和 GBK）。") from None


def _drop_empty_columns(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.dropna(axis=1, how="all")
    keep = [
        column
        for column in frame.columns
        if not str(column).startswith("Unnamed:") or not frame[column].isna().all()
    ]
    return frame.loc[:, keep]


def list_excel_sheets(content: bytes) -> list[str]:
    """Return worksheet names without reading all workbook data."""

    try:
        return pd.ExcelFile(BytesIO(content), engine="openpyxl").sheet_names
    except Exception as exc:  # pandas/openpyxl provide inconsistent exception types
        raise ValueError(f"无法读取 Excel 工作簿：{exc}") from exc


def _detect_excel_header_row(content: bytes, sheet_name: str | int) -> int:
    preview = pd.read_excel(
        BytesIO(content),
        sheet_name=sheet_name,
        header=None,
        nrows=30,
        engine="openpyxl",
    )
    if preview.empty:
        return 0
    scores = preview.apply(lambda row: _alias_score(row.dropna().tolist()), axis=1)
    best_row = int(scores.idxmax())
    return best_row if int(scores.loc[best_row]) >= 2 else 0


def read_table_bytes(
    content: bytes,
    filename: str,
    sheet_name: str | int | None = None,
) -> pd.DataFrame:
    """Read CSV/XLSX bytes, including common Neware title/preamble rows."""

    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        text = _decode_csv(content)
        header_row = _detect_text_header_row(text)
        try:
            frame = pd.read_csv(
                StringIO(text),
                sep=None,
                engine="python",
                skiprows=header_row,
            )
        except Exception as exc:
            raise ValueError(f"CSV 解析失败：{exc}") from exc
    elif suffix in {".xlsx", ".xlsm"}:
        selected_sheet = sheet_name if sheet_name is not None else 0
        try:
            header_row = _detect_excel_header_row(content, selected_sheet)
            frame = pd.read_excel(
                BytesIO(content),
                sheet_name=selected_sheet,
                header=header_row,
                engine="openpyxl",
            )
        except Exception as exc:
            raise ValueError(f"Excel 解析失败：{exc}") from exc
    else:
        raise ValueError("仅支持 .csv、.xlsx 和 .xlsm 文件。")

    frame = _drop_empty_columns(frame)
    if frame.empty or len(frame.columns) == 0:
        raise ValueError("文件中没有可分析的数据。")
    frame.columns = [str(column).strip() for column in frame.columns]
    return frame


def auto_detect_mapping(columns: Iterable[object]) -> dict[str, str | None]:
    """Suggest canonical fields from English/Chinese Neware-like headers."""

    column_names = [str(column) for column in columns]
    normalised = {column: _normalise_name(column) for column in column_names}
    result: dict[str, str | None] = {key: None for key in COLUMN_ALIASES}

    for field, aliases in COLUMN_ALIASES.items():
        normalised_aliases = [_normalise_name(alias) for alias in aliases]
        exact = [
            column
            for column, value in normalised.items()
            if value in normalised_aliases
        ]
        if exact:
            result[field] = exact[0]
            continue
        partial = [
            column
            for column, value in normalised.items()
            if any(alias in value or value in alias for alias in normalised_aliases)
        ]
        if partial:
            result[field] = partial[0]
    return result

