"""위치(z) (용어 표): 같은 조건 대비 차이를 그해까지 여러 해 모아, 연수가 적으면 0 쪽으로 줄여 잡은 선종 내 표준 점수.

[담당: 배성우] 지금 형태: 축소 평균 = 평균 × n/(n+λ).
  기획서 최종형: 해마다 해상 시간에 따른 잡음 크기로 가중(EU 구간 보정), λ 를 데이터로 추정.
  비교 후보(2년 평균, SFA)는 experiments/ 에서 같은 produces 로 만들어 config 에서 바꿔 끼운다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from models.base import FitContext, Stage


class ShrunkPosition(Stage):
    requires = ("imo", "year", "ship_type", "contrib_unexplained")
    produces = ("position_z", "position_n_years", "position_class")

    def __init__(self, shrink_lambda: float = 1.0, **params):
        super().__init__(shrink_lambda=shrink_lambda, **params)

    def _shrunk(self, df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
        g = df["contrib_unexplained"].groupby(df["imo"])
        n = g.cumcount() + 1
        mean = g.cumsum() / n
        lam = float(self.params["shrink_lambda"])
        return mean * n / (n + lam), n

    def fit(self, train: pd.DataFrame, ctx: FitContext) -> "ShrunkPosition":
        super().fit(train, ctx)
        shrunk, _ = self._shrunk(train)
        self.sd = shrunk.groupby(train["ship_type"]).std(ddof=1).to_dict()
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        shrunk, n = self._shrunk(df)
        sd = df["ship_type"].map(self.sd).astype(float)
        z = shrunk / sd
        k = self.thresholds["z_consistently_high"]
        cls = np.where(z >= k, "consistently_high", np.where(z <= -k, "consistently_low", "typical"))
        return pd.DataFrame({"position_z": z, "position_n_years": n.astype("int64"), "position_class": cls.astype(object)}, index=df.index)
