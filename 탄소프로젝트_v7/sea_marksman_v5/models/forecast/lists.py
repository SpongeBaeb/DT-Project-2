"""다음 해 리스트 (회귀 v4 04_final 셀 [3], '2026년 리스트') — 영업 타깃 / 관찰.

규칙 (팀과 같음)
  영업 타깃  p_de_h1 ≥ de_cut (기본 0.8): 다음 해 CII 등급이 D·E 일 확률이 높은 배
  관찰       타깃이 아니고, 이 해 등급이 A~C 이면서 p_miss_h1 ≥ p* (다음 해 감축 요구 미달 확률이 높은 쪽 25%)
  p* = 학습 데이터 마지막 연도 배들의 p_miss_h1 의 watch_quantile(기본 0.75) 분위수. 학습 때 한 번 정해 저장한다
       → 한 척만 넣어도 결과 표와 같은 판정 (API 한 척 = 전체). 학습 때 마지막 연도가 2025 이면 팀의 '2026년 리스트' 기준과 같다.
순위(list_rank)는 같은 리스트 안 배끼리 비교해야 해서 이 Stage 가 아니라 산출물 단계(publish/lists.py)에서 매긴다.
신뢰 등급 표시(list_note: 선종×기간별 검증 등급이 '참고용'인 선종)는 아직 없다 (검증 등급을 새 목표로 다시 계산해야 함).
출력 list_h1: "target" | "watch" | "" (빈칸 = 리스트에 없음, 확률이 없는 행도 빈칸)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from models.base import FitContext, Stage

LISTS = {"target": "영업 타깃", "watch": "관찰"}


class ListRule(Stage):
    requires = ("year", "cii_rating", "p_de_h1", "p_miss_h1")
    produces = ("list_h1",)

    def __init__(self, de_cut: float = 0.8, watch_quantile: float = 0.75, watch_ratings: tuple[str, ...] | list[str] = ("A", "B", "C"), **params):
        super().__init__(de_cut=de_cut, watch_quantile=watch_quantile, watch_ratings=list(watch_ratings), **params)
        self.de_cut, self.watch_quantile, self.watch_ratings = float(de_cut), float(watch_quantile), list(watch_ratings)

    def fit(self, train: pd.DataFrame, ctx: FitContext) -> "ListRule":
        super().fit(train, ctx)
        self.base_year = int(train["year"].max())
        p = train.loc[train["year"] == self.base_year, "p_miss_h1"].dropna()
        if p.empty:
            raise ValueError(f"{self.base_year}년 배의 p_miss_h1 이 없어 관찰 기준 p* 를 정할 수 없습니다 (CII 확률 부품이 앞에 있어야 함)")
        self.p_star = float(p.quantile(self.watch_quantile))
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        target = df["p_de_h1"] >= self.de_cut
        watch = ~target & df["cii_rating"].isin(self.watch_ratings) & (df["p_miss_h1"] >= self.p_star)
        return pd.DataFrame({"list_h1": np.select([target.to_numpy(), watch.to_numpy()], ["target", "watch"], default="")}, index=df.index)

    def describe(self) -> dict:
        d = super().describe()
        d["detail"] = {"base_year": self.base_year, "p_star": round(self.p_star, 6), "de_cut": self.de_cut,
                       "watch_quantile": self.watch_quantile, "watch_ratings": self.watch_ratings}
        return d
