"""같은 조건 기준 모델 (5-1절) — 선종별 ln(해상 효율) 회귀 + 원인 분해.

[담당: 배성우] 지금은 '연도 효과 + 설정의 변수' 단순 OLS. 기획서 최종형으로 바꿀 곳:
  - 경험적 베이즈(선종 간 기울기 공유), 배 단위 군집 오차
  - 변수 확장은 config 만 바꿔도 됨, 예:
      features: {ln_dwt: size, ln_avg_speed_kn: speed_pattern, ln_sea_hours: sea_time,
                 eu_share: eu_exposure, age: age_design, alt_fuel: fuel, has_ice_class: ice}

원인 분해 (약속: 합 == ln(실제/동급 중간), contracts/tables.py CAUSE_FACTORS)
  변수 f 의 기여  = β_f × (x_f − 동급 기준값_f)      동급 기준값 = 학습 때 동급(선종·연도·4분위) 중간값
  other          = ln(예측) − ln(동급 중간) − Σ 변수 기여
  unexplained    = ln(실제) − ln(예측)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from contracts.tables import CAUSE_FACTORS
from models.base import FitContext, Stage
from models.common._linear import feature_values, fit_by_type, predict_by_type


class LinearBaseline(Stage):
    requires = ("ship_type", "year_eff", "size_bin", "sea_eff_kg_nm", "sea_eff_peer_median")
    produces = ("sea_eff_expected", *[f"contrib_{f}" for f in CAUSE_FACTORS])

    def __init__(self, features: dict[str, str] | None = None, **params):
        super().__init__(features=features or {"ln_dwt": "size"}, **params)
        self.features: dict[str, str] = dict(self.params["features"])
        bad = {f: c for f, c in self.features.items() if c not in CAUSE_FACTORS or c in ("other", "unexplained")}
        if bad:
            raise ValueError(f"원인 이름이 잘못됨: {bad}. 가능: {list(CAUSE_FACTORS)[:-2]}")

    def fit(self, train: pd.DataFrame, ctx: FitContext) -> "LinearBaseline":
        super().fit(train, ctx)
        feats = list(self.features)
        self.fits = fit_by_type(train, np.log(train["sea_eff_kg_nm"]), feats)
        x = pd.DataFrame({f: feature_values(train, f) for f in feats}, index=train.index)
        keys = [train["ship_type"], train["year_eff"], train["size_bin"]]
        self.peer_ref = x.groupby(keys).median().to_dict("index")
        self.type_ref = x.groupby([train["ship_type"], train["size_bin"]]).median().to_dict("index")
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        ln_pred = predict_by_type(self.fits, df)
        out = pd.DataFrame(0.0, index=df.index, columns=list(self.produces))
        out["sea_eff_expected"] = np.exp(ln_pred)

        explained = pd.Series(0.0, index=df.index)
        for f, factor in self.features.items():
            x = feature_values(df, f)
            ref = np.array([
                self.peer_ref.get((t, y, b), self.type_ref.get((t, b), {})).get(f, np.nan)
                for t, y, b in zip(df["ship_type"], df["year_eff"], df["size_bin"])
            ])
            beta = df["ship_type"].map(lambda t: self.fits[t].beta(f)).to_numpy(dtype=float)
            fill = df["ship_type"].map(lambda t: self.fits[t].fill[f]).to_numpy(dtype=float)
            c = beta * (x.fillna(pd.Series(fill, index=df.index)).to_numpy() - np.nan_to_num(ref, nan=0.0))
            c = np.where(np.isfinite(ref), c, 0.0)
            out[f"contrib_{factor}"] += c
            explained += c

        out["contrib_other"] = ln_pred - np.log(df["sea_eff_peer_median"]) - explained
        out["contrib_unexplained"] = np.log(df["sea_eff_kg_nm"]) - ln_pred
        return out
