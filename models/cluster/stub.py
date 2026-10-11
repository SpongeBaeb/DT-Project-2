"""선박 유형·운항 이상 (5-4절) — 임시 부품.

[담당: 차희성] 지금은 두 축을 3등분(학습 데이터 33/67% 경계)만 한다. 바꿀 것:
  ① 두 축 K-평균 (EU 규제 노출도 = 역내 비중 × 해상 시간, 선령·설계 = 수명 대비 선령 × 설계 효율)
  ② 운항 지표 군집 후 어느 중심에서도 먼 2.5% → ops_outlier
  같은 produces 를 지키는 새 클래스를 만들고 config 의 use 를 바꾼다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from models.base import FitContext, Stage


def _exposure(df: pd.DataFrame) -> pd.Series:
    return df["eu_share"].fillna(0.0) * df["ln_sea_hours"]


class TertileTypes(Stage):
    requires = ("eu_share", "ln_sea_hours", "age")
    produces = ("type_exposure", "type_age_design", "ops_outlier")

    def fit(self, train: pd.DataFrame, ctx: FitContext) -> "TertileTypes":
        super().fit(train, ctx)
        self.exp_edges = _exposure(train).quantile([1 / 3, 2 / 3]).to_numpy()
        self.age_edges = train["age"].astype(float).quantile([1 / 3, 2 / 3]).to_numpy()
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({
            "type_exposure": pd.array(1 + np.searchsorted(self.exp_edges, _exposure(df), side="right"), dtype="Int64"),
            "type_age_design": pd.array(1 + np.searchsorted(self.age_edges, df["age"].astype(float), side="right"), dtype="Int64"),
            "ops_outlier": np.zeros(len(df), dtype=bool),
        }, index=df.index)
