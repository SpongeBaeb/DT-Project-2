"""정박 배출 비교 (5-1절): ① 같은 조건 예측 대비 ② 이 배의 예년 대비.

[담당: 배성우] 지금 형태: 선종별 ln(정박 CO₂+1) = 연도 + 변수 회귀.
  비율은 0톤 방지를 위해 (실제+1)/(예측+1) 로 계산한다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from models.base import FitContext, Stage
from models.common._linear import fit_by_type, predict_by_type

DEFAULT_FEATURES = ["ln_dwt", "eu_share", "ln_sea_hours", "age"]


class BerthCompare(Stage):
    requires = ("imo", "year", "ship_type", "year_eff", "berth_co2_t")
    produces = ("berth_expected_t", "berth_ratio", "berth_z", "berth_ratio_hist_min", "berth_ratio_hist_max", "berth_hist_z")

    def __init__(self, features: list[str] | None = None, **params):
        super().__init__(features=features or DEFAULT_FEATURES, **params)

    def fit(self, train: pd.DataFrame, ctx: FitContext) -> "BerthCompare":
        super().fit(train, ctx)
        self.fits = fit_by_type(train, np.log1p(train["berth_co2_t"]), list(self.params["features"]))
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        ln_pred = predict_by_type(self.fits, df)
        ln_act = np.log1p(df["berth_co2_t"].astype(float))
        sd = df["ship_type"].map(lambda t: self.fits[t].resid_sd).astype(float)
        log_ratio = ln_act - ln_pred

        # 이 배의 지난 해들 (현재 연도 제외, 미래 연도 사용 안 함)
        g = log_ratio.groupby(df["imo"])
        prior_min = g.transform(lambda s: s.shift().expanding().min())
        prior_max = g.transform(lambda s: s.shift().expanding().max())
        prior_mean = g.transform(lambda s: s.shift().expanding().mean())
        prior_sd = g.transform(lambda s: s.shift().expanding().std(ddof=1))
        prior_n = g.transform(lambda s: s.shift().expanding().count())
        hist_z = (log_ratio - prior_mean) / prior_sd
        hist_z = hist_z.where((prior_n >= 2) & (prior_sd > 0))

        return pd.DataFrame({
            "berth_expected_t": np.expm1(ln_pred).clip(lower=0),
            "berth_ratio": np.exp(log_ratio),
            "berth_z": log_ratio / sd,
            "berth_ratio_hist_min": np.exp(prior_min),
            "berth_ratio_hist_max": np.exp(prior_max),
            "berth_hist_z": hist_z,
        }, index=df.index)
