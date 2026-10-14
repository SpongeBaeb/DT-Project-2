"""선종별 선형 회귀 도우미 (연도 효과 + 변수). 기준 모델·정박 비교가 함께 쓴다.

담당자가 경험적 베이즈·군집 오차 등으로 바꿀 때도 fit_by_type / predict_by_type 의 모양을 유지하면
다른 부품은 손대지 않아도 된다.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def feature_values(df: pd.DataFrame, name: str) -> pd.Series:
    """열 이름 그대로, 또는 'ln_' + 열 이름이면 로그."""
    if name in df.columns:
        return df[name].astype(float)
    if name.startswith("ln_") and name[3:] in df.columns:
        return np.log(df[name[3:]].astype(float))
    raise KeyError(f"변수 {name} 를 만들 수 없습니다 (열 없음)")


@dataclass
class TypeFit:
    years: list[int]
    features: list[str]
    coef: np.ndarray            # [상수, 연도 더미(첫 해 제외)..., 변수...]
    fill: dict[str, float]      # 빈칸 채움값 (학습 중간값)
    resid_sd: float
    n: int

    def design(self, df: pd.DataFrame) -> np.ndarray:
        cols = [np.ones(len(df))]
        ye = df["year_eff"].to_numpy()
        cols += [(ye == y).astype(float) for y in self.years[1:]]
        for f in self.features:
            cols.append(feature_values(df, f).fillna(self.fill[f]).to_numpy(dtype=float))
        return np.column_stack(cols)

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        return self.design(df) @ self.coef

    def beta(self, feature: str) -> float:
        return float(self.coef[len(self.years) + self.features.index(feature)])


def fit_by_type(train: pd.DataFrame, y: pd.Series, features: list[str]) -> dict[str, TypeFit]:
    fits: dict[str, TypeFit] = {}
    for t, g in train.groupby("ship_type"):
        yy = y.loc[g.index].to_numpy(dtype=float)
        ok = np.isfinite(yy)
        g, yy = g.loc[ok], yy[ok]
        fill = {f: float(np.nanmedian(feature_values(g, f))) if feature_values(g, f).notna().any() else 0.0 for f in features}
        tf = TypeFit(years=sorted(g["year_eff"].unique().tolist()), features=list(features), coef=np.zeros(0), fill=fill, resid_sd=np.nan, n=len(g))
        X = tf.design(g)
        coef, *_ = np.linalg.lstsq(X, yy, rcond=None)
        tf.coef = coef
        resid = yy - X @ coef
        dof = max(len(yy) - X.shape[1], 1)
        tf.resid_sd = float(np.sqrt(resid @ resid / dof))
        fits[t] = tf
    return fits


def predict_by_type(fits: dict[str, TypeFit], df: pd.DataFrame) -> pd.Series:
    out = pd.Series(np.nan, index=df.index)
    for t, g in df.groupby("ship_type"):
        out.loc[g.index] = fits[t].predict(g)
    return out
