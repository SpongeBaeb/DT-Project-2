"""착시 신호 5종 (2-3절). 규칙 자체는 shared/checks.py 에 있다 (API 입력 점검과 같은 규칙).

[담당: 차희성·배성우] 특수 운항 집단을 운영사 목록 외에 속력·군집으로도 잡으려면 여기서 확장.
"""
from __future__ import annotations

import pandas as pd

from contracts.tables import SIGNAL_COLS
from models.base import Stage
from shared.checks import illusion_signals


class IllusionSignals(Stage):
    requires = ("berth_z", "berth_hist_z", "avg_speed_kn", "cargo_t", "dwt", "co2_per_fuel", "sea_hours")
    produces = (*SIGNAL_COLS, "sig_any")

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        return illusion_signals(df, self.thresholds)[list(self.produces)]
