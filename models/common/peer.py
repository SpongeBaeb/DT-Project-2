"""동급(선종·연도·크기 4분위)과 동급 중간 해상 효율.

4분위 경계는 학습 때 고정해 모델 파일에 저장한다. 한 척만 입력해도(API) 같은 경계로 같은 4분위가 나온다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from models.base import FitContext, Stage


class PeerGroup(Stage):
    requires = ("ship_type", "year_eff", "dwt", "sea_eff_kg_nm")
    produces = ("size_bin", "sea_eff_peer_median")

    def fit(self, train: pd.DataFrame, ctx: FitContext) -> "PeerGroup":
        super().fit(train, ctx)
        self.edges: dict[tuple[str, int], np.ndarray] = {}
        self.type_edges: dict[str, np.ndarray] = {}
        for t, g in train.groupby("ship_type"):
            self.type_edges[t] = g["dwt"].quantile([0.25, 0.5, 0.75]).to_numpy()
        for (t, y), g in train.groupby(["ship_type", "year_eff"]):
            self.edges[(t, int(y))] = g["dwt"].quantile([0.25, 0.5, 0.75]).to_numpy()

        tb = train.assign(size_bin=self._bins(train))
        self.median = tb.groupby(["ship_type", "year_eff", "size_bin"])["sea_eff_kg_nm"].median().to_dict()
        self.type_bin_median = tb.groupby(["ship_type", "size_bin"])["sea_eff_kg_nm"].median().to_dict()
        return self

    def _bins(self, df: pd.DataFrame) -> np.ndarray:
        out = np.empty(len(df), dtype="int64")
        for i, (t, y, d) in enumerate(zip(df["ship_type"], df["year_eff"], df["dwt"])):
            e = self.edges.get((t, int(y)), self.type_edges[t])
            out[i] = 1 + int(np.searchsorted(e, d, side="right"))
        return out

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        bins = self._bins(df)
        med = [
            self.median.get((t, int(y), b), self.type_bin_median.get((t, b), np.nan))
            for t, y, b in zip(df["ship_type"], df["year_eff"], bins)
        ]
        return pd.DataFrame({"size_bin": bins, "sea_eff_peer_median": np.asarray(med, dtype=float)}, index=df.index)
