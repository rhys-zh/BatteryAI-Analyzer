"""Streamlit entry point for BatteryAI-Analyzer."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from battery_ai.analysis import build_cycle_summary, compute_key_metrics
from battery_ai.anomaly import AnomalyDetectionError, detect_cycle_anomalies
from battery_ai.data_loader import auto_detect_mapping, list_excel_sheets, read_table_bytes
from battery_ai.plotting import (
    anomaly_score_figure,
    cycle_performance_figure,
    voltage_capacity_figure,
)
from battery_ai.validation import prepare_battery_data


APP_ROOT = Path(__file__).resolve().parent
SAMPLE_PATH = APP_ROOT / "example_data" / "synthetic_neware_demo.csv"
TARGET_CYCLES = (1, 5, 10, 20, 50)


st.set_page_config(
    page_title="BatteryAI-Analyzer",
    page_icon="🔋",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .stApp { background: linear-gradient(180deg, #F3F8F6 0, #F8FAF9 280px); }
    [data-testid="stSidebar"] { background: #17332F; }
    [data-testid="stSidebar"] * { color: #F2FAF8; }
    [data-testid="stSidebar"] input,
    [data-testid="stSidebar"] [data-baseweb="select"] * { color: #17332F; }
    .hero {
        padding: 1.45rem 1.65rem 1.25rem;
        border-radius: 18px;
        background: linear-gradient(118deg, #123E38 0%, #0F766E 72%, #35A89B 100%);
        color: white;
        box-shadow: 0 16px 40px rgba(15, 77, 69, .18);
        margin-bottom: 1rem;
    }
    .hero-kicker { font-size: .75rem; letter-spacing: .13em; opacity: .76; font-weight: 700; }
    .hero h1 { color: white; margin: .25rem 0 .35rem; font-size: 2.05rem; }
    .hero p { margin: 0; opacity: .9; max-width: 760px; }
    .section-note {
        border-left: 3px solid #0F766E; padding: .2rem 0 .2rem .8rem;
        color: #47645F; font-size: .9rem; margin-bottom: .75rem;
    }
    div[data-testid="stMetric"] {
        background: rgba(255,255,255,.86); border: 1px solid #DDE9E6;
        border-radius: 14px; padding: .85rem 1rem; box-shadow: 0 5px 18px rgba(24,60,54,.05);
    }
    div[data-testid="stMetricLabel"] { color: #53706B; }
    .method-card {
        padding: 1rem 1.1rem; border: 1px solid #DDE9E6; border-radius: 14px;
        background: white; height: 100%;
    }
    .method-card h4 { margin: 0 0 .45rem; color: #0F766E; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def load_table(content: bytes, filename: str, sheet_name: str | None) -> pd.DataFrame:
    return read_table_bytes(content, filename, sheet_name)


def format_number(value: float, suffix: str, digits: int = 2) -> str:
    if value is None or not np.isfinite(value):
        return "—"
    return f"{value:.{digits}f} {suffix}".strip()


def mapping_select(
    label: str,
    field: str,
    columns: list[str],
    suggestion: dict[str, str | None],
    *,
    required: bool,
) -> str | None:
    options = ["— 未映射 —", *columns]
    proposed = suggestion.get(field)
    index = options.index(proposed) if proposed in options else 0
    value = st.selectbox(
        f"{label}{' *' if required else ''}",
        options,
        index=index,
        key=f"mapping_{field}",
    )
    return None if value == options[0] else value


st.markdown(
    """
    <div class="hero">
      <div class="hero-kicker">BATTERY RESEARCH WORKBENCH</div>
      <h1>BatteryAI-Analyzer</h1>
      <p>从新威测试数据到循环性能、关键指标与可解释的探索性异常线索，一站式完成基础分析。</p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("## 数据工作台")
    uploaded_file = st.file_uploader(
        "上传新威导出文件",
        type=["csv", "xlsx", "xlsm"],
        help="支持 CSV、XLSX、XLSM，单文件上限 200 MB。",
    )
    if uploaded_file is None:
        st.caption("当前使用内置合成演示数据。上传文件后会自动切换。")
        file_content = SAMPLE_PATH.read_bytes()
        filename = SAMPLE_PATH.name
        using_sample = True
    else:
        file_content = uploaded_file.getvalue()
        filename = uploaded_file.name
        using_sample = False

    sheet_name: str | None = None
    if Path(filename).suffix.lower() in {".xlsx", ".xlsm"}:
        try:
            sheets = list_excel_sheets(file_content)
            sheet_name = st.selectbox("工作表", sheets)
        except ValueError as exc:
            st.error(str(exc))
            st.stop()

try:
    raw_data = load_table(file_content, filename, sheet_name)
except ValueError as exc:
    st.error(str(exc))
    st.stop()

suggestions = auto_detect_mapping(raw_data.columns)
column_names = list(raw_data.columns)

with st.sidebar:
    st.markdown("### 列映射")
    st.caption("已按常见中英文列名预选；请以实际导出格式为准。")
    cycle_column = mapping_select("循环序号", "cycle", column_names, suggestions, required=True)
    step_column = mapping_select("工步/状态", "step_type", column_names, suggestions, required=False)
    time_column = mapping_select("时间", "time", column_names, suggestions, required=False)
    voltage_column = mapping_select("电压", "voltage", column_names, suggestions, required=True)
    current_column = mapping_select("电流", "current", column_names, suggestions, required=True)
    capacity_column = mapping_select("容量", "capacity", column_names, suggestions, required=True)

    with st.expander("单位与清洗规则", expanded=False):
        capacity_unit = st.radio("容量单位", ["mAh", "Ah"], horizontal=True)
        current_unit = st.radio("电流单位", ["mA", "A"], horizontal=True)
        time_unit = st.radio("数值时间单位", ["s", "min", "h"], horizontal=True)
        positive_current_is_charge = st.toggle("正电流表示充电", value=True)
        voltage_range = st.slider(
            "有效电压范围 (V)",
            min_value=0.0,
            max_value=10.0,
            value=(0.0, 5.0),
            step=0.1,
        )
        remove_duplicates = st.toggle("移除完全重复记录", value=True)

mapping = {
    "cycle": cycle_column,
    "step_type": step_column,
    "time": time_column,
    "voltage": voltage_column,
    "current": current_column,
    "capacity": capacity_column,
}

try:
    prepared = prepare_battery_data(
        raw_data,
        mapping,
        capacity_unit=capacity_unit,
        current_unit=current_unit,
        time_unit=time_unit,
        positive_current_is_charge=positive_current_is_charge,
        voltage_range=voltage_range,
        remove_duplicates=remove_duplicates,
    )
except ValueError as exc:
    st.warning(str(exc))
    with st.expander("查看原始数据预览", expanded=True):
        st.dataframe(raw_data.head(100), width="stretch", hide_index=True)
    st.stop()

data = prepared.data
summary = build_cycle_summary(data)
if summary.empty:
    st.error("当前映射无法得到充/放电循环汇总。请检查工步列，或确认电流正负号规则。")
    st.stop()

available_reference_cycles = summary.dropna(subset=["discharge_capacity_mah"])["cycle"].astype(int).tolist()
if not available_reference_cycles:
    st.error("没有找到有效放电容量。请检查工步映射、电流正负号和容量列。")
    st.stop()
default_reference_index = (
    available_reference_cycles.index(1) if 1 in available_reference_cycles else 0
)
with st.sidebar:
    st.markdown("### 指标基准")
    reference_cycle = st.selectbox(
        "容量保持率基准循环",
        available_reference_cycles,
        index=default_reference_index,
    )
    st.caption("保持率 = 指定圈放电容量 ÷ 基准圈放电容量 × 100%")
    source_badge = "合成演示数据" if using_sample else filename
    st.markdown(f"**当前数据：** {source_badge}")
    st.caption(f"{len(raw_data):,} 条原始记录 · {summary['cycle'].nunique():,} 个循环")

metrics = compute_key_metrics(summary, TARGET_CYCLES, reference_cycle)
latest = summary.dropna(subset=["discharge_capacity_mah"]).iloc[-1]
latest_retention = (
    float(latest["discharge_capacity_mah"])
    / float(metrics["reference_discharge_capacity_mah"])
    * 100
)

metric_columns = st.columns(4)
metric_columns[0].metric(
    "首次库伦效率",
    format_number(float(metrics["first_coulombic_efficiency_pct"]), "%"),
    help=f"首个充、放电容量均有效的循环：第 {metrics['first_efficiency_cycle']} 圈",
)
metric_columns[1].metric(
    "最新放电容量",
    format_number(float(latest["discharge_capacity_mah"]), "mAh", 3),
    f"第 {int(latest['cycle'])} 圈",
)
metric_columns[2].metric(
    "最新容量保持率",
    format_number(latest_retention, "%"),
    f"相对第 {metrics['reference_cycle']} 圈",
)
metric_columns[3].metric("有效数据率", f"{prepared.output_rows / prepared.input_rows * 100:.1f}%", f"{prepared.output_rows:,} 条")

if using_sample:
    st.info(
        "当前展示的是程序生成的合成演示数据，仅用于验证交互和计算流程，不代表任何真实电池或模型性能。",
        icon="🧪",
    )

overview_tab, curves_tab, anomaly_tab, quality_tab, method_tab = st.tabs(
    ["循环总览", "充放电曲线", "异常探索", "数据质量", "方法说明"]
)

with overview_tab:
    st.markdown("### 循环性能")
    st.markdown(
        '<div class="section-note">容量取每一循环对应充/放电阶段的最大累计容量；虚线为库伦效率。</div>',
        unsafe_allow_html=True,
    )
    st.plotly_chart(cycle_performance_figure(summary), use_container_width=True)

    st.markdown("### 指定循环容量保持率")
    retention_table = metrics["retentions"].copy()
    retention_table["状态"] = np.where(retention_table["retention_pct"].isna(), "该循环不存在", "已计算")
    retention_table = retention_table.rename(
        columns={
            "cycle": "循环",
            "discharge_capacity_mah": "放电容量 (mAh)",
            "retention_pct": "容量保持率 (%)",
        }
    )
    st.dataframe(
        retention_table,
        width="stretch",
        hide_index=True,
        column_config={
            "放电容量 (mAh)": st.column_config.NumberColumn(format="%.3f"),
            "容量保持率 (%)": st.column_config.NumberColumn(format="%.2f%%"),
        },
    )

with curves_tab:
    st.markdown("### 代表性充放电曲线")
    available_cycles = set(data["cycle"].unique())
    selected_cycles = [cycle for cycle in TARGET_CYCLES if cycle in available_cycles]
    missing_cycles = [cycle for cycle in TARGET_CYCLES if cycle not in available_cycles]
    if missing_cycles:
        st.caption("未绘制缺失循环：" + "、".join(map(str, missing_cycles)))
    if selected_cycles:
        st.plotly_chart(
            voltage_capacity_figure(data, selected_cycles),
            use_container_width=True,
        )
        st.caption("同色代表同一循环；实线为充电，点线为放电。")
    else:
        st.warning("数据中没有第 1、5、10、20、50 圈。")

    custom_cycles = st.multiselect(
        "追加查看其他循环",
        options=sorted(available_cycles),
        max_selections=8,
    )
    if custom_cycles:
        st.plotly_chart(voltage_capacity_figure(data, custom_cycles), use_container_width=True)

with anomaly_tab:
    st.markdown("### Isolation Forest 探索性异常检测")
    st.markdown(
        '<div class="section-note">模型在循环级特征空间中寻找相对孤立的样本。分数低于 0 即按当前预期异常比例标记，属于筛查线索而非失效诊断。</div>',
        unsafe_allow_html=True,
    )
    contamination = st.slider(
        "预期异常比例",
        min_value=0.02,
        max_value=0.30,
        value=0.08,
        step=0.01,
        help="Isolation Forest 必须预先指定预计异常占比；调整它会直接改变判定边界。",
    )
    try:
        anomaly_result, anomaly_metadata = detect_cycle_anomalies(
            summary,
            contamination=contamination,
        )
        anomaly_count = int(anomaly_result["is_anomaly"].sum())
        info_columns = st.columns(3)
        info_columns[0].metric("参与循环", anomaly_metadata["n_cycles"])
        info_columns[1].metric("标记异常", anomaly_count)
        info_columns[2].metric("判定边界", "分数 < 0")
        st.plotly_chart(anomaly_score_figure(anomaly_result), use_container_width=True)

        st.markdown("#### 被标记循环与辅助判据")
        anomaly_table = anomaly_result[anomaly_result["is_anomaly"]].copy()
        anomaly_table = anomaly_table.rename(
            columns={
                "cycle": "循环",
                "anomaly_score": "判定分数",
                "reason": "相对中位水平的偏离线索",
            }
        )
        display_columns = ["循环", "判定分数", "相对中位水平的偏离线索"]
        st.dataframe(
            anomaly_table[display_columns],
            width="stretch",
            hide_index=True,
            column_config={"判定分数": st.column_config.NumberColumn(format="%.4f")},
        )
        st.caption("使用特征：" + "、".join(anomaly_metadata["feature_labels"]))
        st.warning(
            "局限性：这是无监督、相对型检测；结果依赖数据质量、所选特征与预期异常比例。"
            "被标记不等于电池失效，未标记也不代表安全或正常，必须结合测试日志、工况和电化学机理复核。",
            icon="⚠️",
        )
    except AnomalyDetectionError as exc:
        st.info(str(exc))

with quality_tab:
    st.markdown("### 数据校验与处理记录")
    quality_columns = st.columns(3)
    quality_columns[0].metric("原始记录", f"{prepared.input_rows:,}")
    quality_columns[1].metric("清洗后记录", f"{prepared.output_rows:,}")
    quality_columns[2].metric("剔除记录", f"{prepared.input_rows - prepared.output_rows:,}")
    st.dataframe(prepared.quality_report, width="stretch", hide_index=True)
    st.caption("所有规则均在侧栏可见；原始上传文件不会被修改。")

    preview_raw, preview_clean = st.columns(2)
    with preview_raw:
        st.markdown("#### 原始数据预览")
        st.dataframe(raw_data.head(100), width="stretch", hide_index=True, height=330)
    with preview_clean:
        st.markdown("#### 标准化数据预览")
        st.dataframe(data.head(100), width="stretch", hide_index=True, height=330)

    st.download_button(
        "下载标准化数据 CSV",
        data=data.to_csv(index=False).encode("utf-8-sig"),
        file_name="batteryai_cleaned_data.csv",
        mime="text/csv",
    )

with method_tab:
    st.markdown("### 计算口径")
    method_columns = st.columns(3)
    with method_columns[0]:
        st.markdown(
            """
            <div class="method-card"><h4>循环容量</h4>
            同一循环内，分别取充电与放电记录中的最大累计容量。适用于容量在工步内从 0 累加的常见新威导出格式。</div>
            """,
            unsafe_allow_html=True,
        )
    with method_columns[1]:
        st.markdown(
            """
            <div class="method-card"><h4>首次库伦效率</h4>
            首个同时存在有效充、放电容量的循环：放电容量 ÷ 充电容量 × 100%。不强制假设它一定是第 1 圈。</div>
            """,
            unsafe_allow_html=True,
        )
    with method_columns[2]:
        st.markdown(
            """
            <div class="method-card"><h4>容量保持率</h4>
            指定循环放电容量 ÷ 侧栏所选基准循环放电容量 × 100%。缺失循环显示为空，不做插值。</div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("### 使用边界")
    st.markdown(
        """
        - 当前版本面向恒流/恒压循环数据的探索性分析，不替代新威原厂软件、质量体系或安全判定。
        - 不同设备模板和测试规程可能使用不同符号、容量复位方式或多级工步；分析前必须核对列映射与计算口径。
        - 平均电压是记录点的算术平均，并非严格的容量加权平台电压。
        - Isolation Forest 没有使用故障标签，也未报告准确率、召回率等监督学习性能指标。
        """
    )

