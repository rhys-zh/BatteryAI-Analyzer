from io import BytesIO

import pandas as pd

from battery_ai.data_loader import auto_detect_mapping, list_excel_sheets, read_table_bytes


def test_csv_with_neware_preamble_is_detected():
    content = (
        "Neware Battery Test Export\n"
        "Device,CT-4008\n"
        "Cycle ID,Step Type,Voltage(V),Current(mA),Capacity(mAh)\n"
        "1,CC Chg,3.1,50,10\n"
    ).encode()
    frame = read_table_bytes(content, "demo.csv")
    assert list(frame.columns) == [
        "Cycle ID",
        "Step Type",
        "Voltage(V)",
        "Current(mA)",
        "Capacity(mAh)",
    ]
    assert len(frame) == 1


def test_auto_detect_mapping_supports_chinese_headers():
    mapping = auto_detect_mapping(["循环序号", "工步类型", "电压(V)", "电流(mA)", "容量(mAh)"])
    assert mapping["cycle"] == "循环序号"
    assert mapping["step_type"] == "工步类型"
    assert mapping["voltage"] == "电压(V)"


def test_excel_sheet_reading():
    buffer = BytesIO()
    source = pd.DataFrame(
        {"Cycle ID": [1], "Voltage(V)": [3.2], "Current(mA)": [50], "Capacity(mAh)": [1]}
    )
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        source.to_excel(writer, sheet_name="record", index=False)
    content = buffer.getvalue()
    assert list_excel_sheets(content) == ["record"]
    result = read_table_bytes(content, "test.xlsx", "record")
    pd.testing.assert_frame_equal(result, source, check_dtype=False)

