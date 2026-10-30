"""Generate deterministic, explicitly synthetic Neware-like demonstration data."""

from pathlib import Path

import numpy as np
import pandas as pd


def generate_sample() -> pd.DataFrame:
    rng = np.random.default_rng(20261028)
    rows: list[dict[str, object]] = []
    elapsed = 0
    for cycle in range(1, 61):
        fade = 1.0 - 0.0016 * (cycle - 1)
        charge_capacity = 105.0 * fade
        efficiency = 0.92 if cycle == 1 else 0.985 + 0.003 * np.exp(-cycle / 12)
        scenario = "baseline"
        if cycle == 18:
            charge_capacity *= 0.88
            scenario = "synthetic capacity dip"
        if cycle == 42:
            efficiency *= 0.90
            scenario = "synthetic efficiency dip"
        discharge_capacity = charge_capacity * efficiency

        for state, maximum, current in (
            ("CC-CV Chg", charge_capacity, 50.0),
            ("CC DChg", discharge_capacity, -50.0),
        ):
            for point in range(31):
                fraction = point / 30
                capacity = maximum * fraction
                if state == "CC-CV Chg":
                    voltage = 2.15 + 2.03 * fraction + 0.05 * np.tanh((fraction - 0.7) * 8)
                else:
                    voltage = 4.12 - 2.02 * fraction - 0.06 * np.tanh((fraction - 0.72) * 7)
                voltage += rng.normal(0, 0.003)
                rows.append(
                    {
                        "Cycle ID": cycle,
                        "Step Type": state,
                        "TestTime(s)": elapsed,
                        "Voltage(V)": round(voltage, 5),
                        "Current(mA)": current,
                        "Capacity(mAh)": round(capacity, 5),
                        "Data Origin": "SYNTHETIC DEMO — NOT EXPERIMENTAL DATA",
                        "Synthetic Scenario": scenario,
                    }
                )
                elapsed += 72
    return pd.DataFrame(rows)


if __name__ == "__main__":
    destination = Path(__file__).resolve().parents[1] / "example_data" / "synthetic_neware_demo.csv"
    destination.parent.mkdir(parents=True, exist_ok=True)
    generate_sample().to_csv(destination, index=False, encoding="utf-8-sig")
    print(f"Wrote {destination}")

