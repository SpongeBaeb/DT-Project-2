"""유지 확률 — "점검 필요 판정을 받은 배가 이듬해에도 같은 조건보다 10% 넘게 더 쓸 확률" (방현수 님 `08_유지확률` 이식).

원본(persist_common.py, 03_final)과 같은 것
  라벨   t+1년 같은 조건 대비 차이(잔차)가 ln(1.10) 초과. t+1년 보고가 없으면 라벨 없음
  학습   모든 배·연도 쌍 (점검 필요 배만 쓰면 한 해 200~270척뿐), 학습 기간에 라벨이 알려진 쌍만
  모델   LightGBM (원본 최종 설정 persist-1.2: 롤링 검증에서 선택), 재보정 없음
  요인   트리 SHAP 기여를 변수 묶음으로 합쳐 "확률을 가장 높이는·낮추는 요인" 이름 (원본 REASON_GROUPS)
이식하면서 바뀐 것 (원본은 구 공통잔차 결과 common_residual.parquet 를 읽음 → 이 프레임워크의 앞 Stage 열로 대신함)
  resid_c        → contrib_unexplained (같은 조건 예상 대비 차이, 로그. 원본과 상관 0.95)
  z              → position_z (줄여 잡은 평균의 선종 내 표준 점수, 같은 공식. 원본과 상관 0.97)
  gap(동급 대비) → ln(해상 효율 ÷ 동급 중간값) (원본과 상관 0.92)
  c_berth        → ln(berth_ratio) 정박 배출 ÷ 같은 조건 예상 (원본의 정박 기여와 상관 0.56. 정의가 다름)
  shrink_k       → 학습 때 선종별로 추정해 고정한 σ²_배, σ²_해마다 로 k = σ²_배 ÷ (σ²_배 + σ²_해마다 ÷ 보고 연수)
규칙: 한 배의 값은 그 배의 그해까지 행과 학습 때 고정한 값만으로 계산된다 (API 한 척 = 전체, 미래 연도 값 없음).
출력은 모든 배·연도에 채우지만 의미가 있는 것은 점검 필요(position_z ≥ z_consistently_high) 배다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier

from models.base import FitContext, Stage

NUM_FEATS = ("z", "resid", "self_delta", "n_years", "shrink_k", "ln_sea", "z_x_sea", "gap", "ln_berth")
BIN_FEATS = ("short_sea", "no_past")
# 화면의 "확률을 높이는/낮추는 요인": 관련 변수를 묶은 이름 (상호작용 항이 따로 보이지 않게)
REASON_GROUPS = {
    "판정값 크기": ["z"],
    "EU 해상 시간": ["ln_sea", "z_x_sea", "short_sea"],
    "올해 같은 조건 대비 차이": ["resid"],
    "동급 대비 격차": ["gap"],
    "자기 과거 대비 변화": ["self_delta", "no_past"],
    "보고 연수": ["n_years", "shrink_k"],
    "정박 배출": ["ln_berth"],
}
LGB = dict(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=50, subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1)


class PersistProbability(Stage):
    requires = ("imo", "year", "year_eff", "ship_type", "sea_eff_kg_nm", "sea_eff_peer_median", "sea_hours", "contrib_unexplained",
                "position_z", "position_n_years", "berth_ratio")
    produces = ("persist_prob", "persist_up", "persist_down")

    def __init__(self, lift: float = 1.10, n_jobs: int | None = None, **params):
        super().__init__(lift=lift, n_jobs=n_jobs, **params)
        self.lift, self.n_jobs = float(lift), n_jobs

    # ───────────── 입력 변수 (그 배의 그해까지 행 + 학습 때 고정한 값) ─────────────
    def _centered(self, df: pd.DataFrame) -> pd.Series:
        """선종·연도 중간값을 뺀 잔차 (EmpiricalBayesPosition 과 같은 중심 맞춤)."""
        keys = zip(df["ship_type"], df["year_eff"].astype(int))
        center = np.array([self.center.get(k, self.type_center.get(k[0], 0.0)) for k in keys])
        return df["contrib_unexplained"].astype(float).to_numpy() - center

    def features(self, df: pd.DataFrame) -> pd.DataFrame:
        d = df.sort_values(["imo", "year"], kind="mergesort")
        resid = d["contrib_unexplained"].astype(float)
        past = resid.groupby(d["imo"]).transform(lambda s: s.shift(1).expanding().mean())
        n = d["position_n_years"].astype(float)
        sb = d["ship_type"].map(self.var_ship).astype(float)
        sw = d["ship_type"].map(self.var_year).astype(float)
        sea = d["sea_hours"].astype(float)
        ln_sea = np.log(sea.clip(lower=1.0))
        z = d["position_z"].astype(float)
        X = pd.DataFrame({
            "z": z, "resid": resid, "self_delta": (resid - past).fillna(0.0), "n_years": n, "shrink_k": sb / (sb + sw / n), "ln_sea": ln_sea,
            "z_x_sea": z * (ln_sea - np.log(float(self.thresholds["short_sea_hours"]))),
            "gap": np.log(d["sea_eff_kg_nm"].astype(float) / d["sea_eff_peer_median"].astype(float)),
            "ln_berth": np.log(d["berth_ratio"].astype(float).clip(lower=1e-3)),
            "short_sea": (sea < float(self.thresholds["short_sea_hours"])).astype(float), "no_past": past.isna().astype(float),
        }, index=d.index)
        for t in self.types[1:]:
            X[f"type={t}"] = (d["ship_type"] == t).astype(float)
        return X.reindex(df.index)

    # ───────────── 학습 ─────────────
    def pairs(self, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
        """입력 변수와 라벨 (t+1년 행이 있는 쌍만). 반환은 (X, y)."""
        X = self.features(df)
        nxt = df[["imo", "year", "contrib_unexplained"]].assign(year=lambda x: x["year"] - 1).rename(columns={"contrib_unexplained": "next_resid"})
        m = df[["imo", "year"]].merge(nxt, on=["imo", "year"], how="left")
        ok = m["next_resid"].notna().to_numpy()
        y = pd.Series((m["next_resid"].to_numpy() > np.log(self.lift)).astype(float), index=df.index)
        return X[ok], y[ok]

    def fit(self, train: pd.DataFrame, ctx: FitContext) -> "PersistProbability":
        super().fit(train, ctx)
        u = train["contrib_unexplained"].astype(float)
        self.center = u.groupby([train["ship_type"], train["year_eff"].astype(int)]).median().to_dict()
        self.type_center = u.groupby(train["ship_type"]).median().to_dict()
        self.types = sorted(train["ship_type"].astype(str).unique())
        r = pd.Series(self._centered(train), index=train.index)
        self.var_ship, self.var_year = {}, {}
        for t, g in r.groupby(train["ship_type"]):
            ships = train.loc[g.index, "imo"]
            mean, n = g.groupby(ships).mean(), g.groupby(ships).size()
            sw = float(((g - ships.map(mean)) ** 2).sum() / max(len(g) - len(mean), 1))
            self.var_ship[t] = max(float(mean.var()) - sw * float((1 / n).mean()), 1e-6)
            self.var_year[t] = sw
        d = train.sort_values(["imo", "year"], kind="mergesort")
        X, y = self.pairs(d)
        if y.nunique() < 2:
            raise ValueError("유지 확률 학습 쌍에 라벨이 한 종류뿐입니다 (연속 연도 쌍이 부족함)")
        self.columns = list(X.columns)
        self.model = LGBMClassifier(**LGB, random_state=int(ctx.seed), n_jobs=self.n_jobs).fit(X, y)
        self.n_pairs, self.base_rate = int(len(y)), float(y.mean())
        return self

    # ───────────── 예측 ─────────────
    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        X = self.features(df)[self.columns]
        p = self.model.predict_proba(X)[:, 1]
        C = pd.DataFrame(self.model.booster_.predict(X, pred_contrib=True)[:, :-1], columns=self.columns, index=df.index)
        G = pd.DataFrame({g: C[[c for c in cols if c in C]].sum(axis=1) for g, cols in REASON_GROUPS.items()})
        up = G.idxmax(axis=1).where(G.max(axis=1) > 0, None)
        down = G.idxmin(axis=1).where(G.min(axis=1) < 0, None)
        ok = df["position_z"].notna().to_numpy()
        return pd.DataFrame({"persist_prob": np.where(ok, p, np.nan), "persist_up": up.where(ok, None).astype(object), "persist_down": down.where(ok, None).astype(object)}, index=df.index)

    def describe(self) -> dict:
        d = super().describe()
        d["detail"] = {"pairs": self.n_pairs, "base_rate": round(self.base_rate, 4), "features": len(self.columns), "origin": "방현수 08_유지확률 persist-1.2"}
        return d
