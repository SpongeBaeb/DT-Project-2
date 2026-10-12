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


class EmpiricalBayesPosition(Stage):
    """줄여 잡은 평균 위치(z) — 배성우 님 `공통잔차/common_residual.py` 의 판정값(R-06)을 Stage 로 옮긴 것.

    배마다 그해까지 잔차(선종·연도 중간값을 뺀 unexplained)의 평균에 k 를 곱한다.
        k = σ²_배 / (σ²_배 + σ²_해마다 / 보고 연수),   z = (k × 평균 − 선종 중간값) / 선종 퍼짐
    보고 연수가 적을수록 k 가 작아 선종 평균 쪽으로 더 줄어든다. σ² 는 학습 때 선종별로 추정해 고정한다.
    그해까지만 쓰므로(누적) 미래 정보가 섞이지 않고, 한 척 입력(API)도 같은 값이 나온다.
    ShrunkPosition 과 같은 produces 라서 config 의 use 만 바꾸면 된다.
    """
    requires = ("imo", "year", "ship_type", "year_eff", "contrib_unexplained")
    produces = ("position_z", "position_n_years", "position_class")

    def _centered(self, df: pd.DataFrame) -> pd.Series:
        keys = list(zip(df["ship_type"], df["year_eff"].astype(int)))
        center = np.array([self.center.get(k, self.type_center.get(k[0], 0.0)) for k in keys])
        return df["contrib_unexplained"].astype(float) - center

    def fit(self, train: pd.DataFrame, ctx: FitContext) -> "EmpiricalBayesPosition":
        super().fit(train, ctx)
        u = train["contrib_unexplained"].astype(float)
        self.center = u.groupby([train["ship_type"], train["year_eff"].astype(int)]).median().to_dict()
        self.type_center = u.groupby(train["ship_type"]).median().to_dict()
        r = self._centered(train)
        self.var_ship: dict[str, float] = {}
        self.var_year: dict[str, float] = {}
        self.med: dict[str, float] = {}
        self.sd: dict[str, float] = {}
        for t, g in r.groupby(train["ship_type"]):
            ships = train.loc[g.index, "imo"]
            mean, n = g.groupby(ships).mean(), g.groupby(ships).size()
            sw = float(((g - ships.map(mean)) ** 2).sum() / max(len(g) - len(mean), 1))
            sb = max(float(mean.var()) - sw * float((1 / n).mean()), 1e-6)
            shrunk = mean * (sb / (sb + sw / n))
            self.var_ship[t], self.var_year[t] = sb, sw
            self.med[t], self.sd[t] = float(shrunk.median()), float(shrunk.std())
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        r = self._centered(df)
        g = r.groupby(df["imo"])
        n = g.cumcount() + 1
        mean = g.cumsum() / n
        sb = df["ship_type"].map(self.var_ship).astype(float)
        sw = df["ship_type"].map(self.var_year).astype(float)
        shrunk = mean * sb / (sb + sw / n)
        z = (shrunk - df["ship_type"].map(self.med).astype(float)) / df["ship_type"].map(self.sd).astype(float)
        k = self.thresholds["z_consistently_high"]
        cls = np.where(z >= k, "consistently_high", np.where(z <= -k, "consistently_low", "typical"))
        return pd.DataFrame({"position_z": z, "position_n_years": n.astype("int64"), "position_class": cls.astype(object)}, index=df.index)
