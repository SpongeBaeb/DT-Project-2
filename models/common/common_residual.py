"""공통 잔차 기준 모델 (5-1절) — 선종별 ln(해상 효율) 회귀 + 원인 분해. 배성우 님의 `공통잔차/common_residual.py`(형식 1.0, 2026-10-08)를 Stage 로 옮긴 것.

LinearBaseline 과 같은 requires/produces 이므로 config 의 use 만 바꾸면 끼워진다.

원본 모델에서 가져온 것
  - 선종마다 따로, 전 연도 함께 추정 (연도 효과 = year_eff 더미)
  - 크기·속력의 2차항, 내빙 등급 둘(높음 IA·IA Super·PC / 낮음 IB·IC), 대체연료, 로팩스 고속선
  - 설계 효율 지표: 값은 (선종×종류) 중앙값과의 차이, 종류 표시(EEDI·EEXI·없음). 종류는 SHIP_YEAR.eedi_kind
  - 선종 간 정보 공유 (DerSimonian–Laird 경험적 베이즈): 뜻이 같은 변수의 기울기를 불확실한 만큼 전체 평균 쪽으로 당김
  - 오차는 배 단위 군집 오차 → `coefficient_table()`, `cause_se()`
  - 속력 탄력성이 elast_wait 이하인 선종은 속력 막대를 "대기 추정"으로 해석 (`type_info[t]["speed_is_wait"]`)
원본과 다른 것 (프레임워크 약속에 맞춘 부분)
  - 목표는 해상 효율(정박 제외 kg/nm). 정박 비중은 변수가 아니다 (정박은 BerthCompare 가 따로 다룸)
  - 고속선(hsc_proxy)은 별도 막대가 없어 `age_design`(선령·설계) 막대에 합친다
  - 대체연료는 shared/preprocess 의 alt_fuel(= max(0, 3.11 − CO₂÷연료)). 원본은 CO₂÷연료 < 3.05 표시
  - 동급 기준값 = PeerGroup 의 동급 중간 해상 효율. 모델이 배분 못 한 나머지는 `other` 칸
  - 크기는 `size` 인자(기본 ln_dwt). 팀 설정은 ln_cii_capacity (선종에 따라 재화중량 또는 총톤수), PeerGroup 의 size_col 과 맞춘다

원인 분해 (약속: 합 == ln(실제/동급 중간), contracts/tables.py)
  막대 f = Σ(그 요인의 변수 계수 × (이 배 값 − 동급 중간 값)),  동급 = 학습 때 고정한 (선종, 연도, 크기 4분위)
  other = ln(예측) − ln(동급 중간) − Σ 막대,   unexplained = ln(실제) − ln(예측)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from contracts.tables import CAUSE_FACTORS
from models.base import FitContext, Stage
from models.common._linear import feature_values

ICE_HI = {"IA", "IA Super", "PC1", "PC2", "PC3", "PC4", "PC5", "PC6", "PC7"}
ICE_LO = {"IB", "IC"}
DESIGN_KINDS = ("EEDI", "EEXI", "EIV")
SPEED_BASE = "ln_avg_speed_kn"
# 선종 간 뜻이 같아 기울기를 당겨도 되는 변수 (원본 POOL 에서 정박을 뺀 것)
POOL_DEFAULT = ["eu_share", "ln_sea_hours", "age", "design_eff", "ice_hi", "ice_lo", "alt_fuel"]


def default_groups(size: str = "ln_dwt") -> dict[str, list[str]]:
    """원인 이름 → 변수 목록. 'x^2' 는 x 의 제곱. design_*·ice_*·hsc_proxy 는 이 모델이 만드는 변수."""
    return {
        "size": [size, f"{size}^2"],
        "speed_pattern": [SPEED_BASE, f"{SPEED_BASE}^2"],
        "sea_time": ["ln_sea_hours"],
        "eu_exposure": ["eu_share"],
        "age_design": ["age", "design_eff", "design_EEDI", "design_EEXI", "design_none", "hsc_proxy"],
        "fuel": ["alt_fuel"],
        "ice": ["ice_hi", "ice_lo"],
    }


def pool_slopes(first: dict[str, tuple[pd.Series, pd.DataFrame]], pool: list[str]) -> dict[str, dict[str, tuple[float, float]]]:
    """선종별 기울기를 불확실한 만큼 전체 평균 쪽으로 당긴다 (DerSimonian–Laird 경험적 베이즈).
    first = {선종: (계수, 공분산)}. 돌려주는 값 = {선종: {변수: (당긴 기울기, 당긴 분산)}}. 변수를 가진 선종이 3개 미만이면 당기지 않는다."""
    out: dict[str, dict[str, tuple[float, float]]] = {t: {} for t in first}
    for v in pool:
        ts = [t for t in first if v in first[t][0].index and first[t][1].loc[v, v] > 0]
        if len(ts) < 3:
            continue
        b = np.array([first[t][0][v] for t in ts])
        s2 = np.array([first[t][1].loc[v, v] for t in ts])
        w = 1 / s2
        mu0 = (w * b).sum() / w.sum()
        q = (w * (b - mu0) ** 2).sum()
        tau2 = max(0.0, (q - (len(b) - 1)) / (w.sum() - (w**2).sum() / w.sum()))
        ws = 1 / (s2 + tau2)
        mu = (ws * b).sum() / ws.sum()
        for t, bi, si2 in zip(ts, b, s2):
            k = tau2 / (tau2 + si2) if tau2 > 0 else 0.0
            out[t][v] = (mu + (bi - mu) * k, si2 * k if tau2 > 0 else 1 / ws.sum())
    return out


class CommonResidualBaseline(Stage):
    requires = ("ship_type", "year_eff", "size_bin", "sea_eff_kg_nm", "sea_eff_peer_median")
    produces = ("sea_eff_expected", *[f"contrib_{f}" for f in CAUSE_FACTORS])

    def __init__(self, groups: dict[str, list[str]] | None = None, size: str = "ln_dwt", elast_wait: float = 0.1,
                 pooling: bool = True, pool: list[str] | None = None, features: dict[str, str] | None = None, **params):
        """features 는 LinearBaseline 과 같은 {변수: 원인 이름} 형식이다. 주면 groups 대신 이것만 쓴다
        (evaluation 이 '크기만 보정한 비교 기준'을 만들 때 features 를 덮어쓰기 때문에 같은 인자를 받아야 한다)."""
        super().__init__(groups=groups, size=size, elast_wait=elast_wait, pooling=pooling, pool=pool, features=features, **params)
        if features:
            by_cause: dict[str, list[str]] = {}
            for token, cause in features.items():
                by_cause.setdefault(cause, []).append(token)
            self.groups = by_cause
        else:
            self.groups = {k: list(v) for k, v in (groups or default_groups(size)).items()}
        bad = [g for g in self.groups if g not in CAUSE_FACTORS or g in ("other", "unexplained")]
        if bad:
            raise ValueError(f"원인 이름이 잘못됨: {bad}. 가능: {list(CAUSE_FACTORS)[:-2]}")
        self.tokens = [t for toks in self.groups.values() for t in toks]
        self.pool = list(pool if pool is not None else POOL_DEFAULT)
        self.pooling = bool(pooling) and not features          # '크기만' 비교 기준에는 당길 변수가 없다

    # ───────────────────────── 변수 만들기 ─────────────────────────
    @staticmethod
    def _kind(df: pd.DataFrame) -> pd.Series:
        k = df["eedi_kind"] if "eedi_kind" in df.columns else pd.Series(None, index=df.index, dtype=object)
        return k.where(k.isin(DESIGN_KINDS), "none").fillna("none")

    def _ln_design(self, df: pd.DataFrame) -> pd.Series:
        e = df["eedi"] if "eedi" in df.columns else pd.Series(np.nan, index=df.index)
        return np.log(e.where(e > 0).astype(float)).where(self._kind(df) != "none")

    def _raw(self, df: pd.DataFrame, token: str) -> pd.Series:
        if token.endswith("^2"):
            return self._raw(df, token[:-2]) ** 2
        if token == "design_eff":                      # 설계 지표 값 − (선종×종류) 중앙값, 없으면 0
            ref = pd.Series(list(zip(df["ship_type"], self._kind(df))), index=df.index).map(self.design_ref).astype(float)
            return (self._ln_design(df) - ref).fillna(0.0)
        if token in ("design_EEDI", "design_EEXI"):
            return (self._kind(df) == token[7:]).astype(float)
        if token == "design_none":
            return ((self._kind(df) == "none") | self._ln_design(df).isna()).astype(float)
        if token == "ice_hi":
            return (df["ice_class"].fillna("").isin(ICE_HI)).astype(float) if "ice_class" in df.columns else pd.Series(0.0, index=df.index)
        if token == "ice_lo":
            return (df["ice_class"].fillna("").isin(ICE_LO)).astype(float) if "ice_class" in df.columns else pd.Series(0.0, index=df.index)
        return feature_values(df, token)

    def _x(self, df: pd.DataFrame) -> pd.DataFrame:
        """변수 표 (빈칸은 선종별 학습 중간값으로 채움)."""
        x = pd.DataFrame({t: self._raw(df, t) for t in self.tokens}, index=df.index)
        for t, g in x.groupby(df["ship_type"]):
            x.loc[g.index] = g.fillna(self.fill[t])
        return x

    # ───────────────────────── 학습 ─────────────────────────
    def fit(self, train: pd.DataFrame, ctx: FitContext) -> "CommonResidualBaseline":
        super().fit(train, ctx)
        self.design_ref: dict[tuple, float] = {}
        if {"design_eff", "design_EEDI", "design_EEXI", "design_none"} & set(self.tokens):
            ln_e = self._ln_design(train)
            key = pd.Series(list(zip(train["ship_type"], self._kind(train))), index=train.index)
            self.design_ref = ln_e.groupby(key).median().dropna().to_dict()
        self.fill: dict[str, pd.Series] = {}
        self.fits: dict[str, dict] = {}
        self.peer_ref: dict[tuple, np.ndarray] = {}
        self.type_ref: dict[tuple, np.ndarray] = {}
        self.type_info: dict[str, dict] = {}

        y_all = np.log(train["sea_eff_kg_nm"].astype(float))
        data: dict[str, tuple[pd.DataFrame, np.ndarray, pd.DataFrame]] = {}
        for t, g in train.groupby("ship_type"):
            raw = pd.DataFrame({k: self._raw(g, k) for k in self.tokens}, index=g.index)
            self.fill[t] = raw.median().fillna(0.0)
            x = raw.fillna(self.fill[t])
            data[t] = (x, y_all.loc[g.index].to_numpy(float), g)
            keys = [g["year_eff"], g["size_bin"]]
            for (yr, b), v in x.groupby(keys).median().iterrows():
                self.peer_ref[(t, int(yr), int(b))] = v.to_numpy(float)
            for b, v in x.groupby(g["size_bin"]).median().iterrows():
                self.type_ref[(t, int(b))] = v.to_numpy(float)

        first = {t: self._ols(*d, fixed={}) for t, d in data.items()}
        pooled = pool_slopes({t: (f["coef"], f["cov"]) for t, f in first.items()}, self.pool) if self.pooling else {t: {} for t in data}
        for t, d in data.items():
            self.fits[t] = self._ols(*d, fixed=pooled[t]) if pooled[t] else first[t]
            self.type_info[t] = self._info(t, d[0])
        return self

    def _ols(self, x: pd.DataFrame, y: np.ndarray, g: pd.DataFrame, fixed: dict[str, tuple[float, float]]) -> dict:
        ok = np.isfinite(y)
        x, y, g = x.loc[ok], y[ok], g.loc[ok]
        cols = [c for c in x.columns if x[c].std() > 0]                 # 변동 없는 변수(예: 내빙선이 없는 선종)는 뺀다
        fixed = {c: v for c, v in fixed.items() if c in cols}           # 당겨 온 기울기는 고정하고 나머지만 맞춘다
        est = [c for c in cols if c not in fixed]
        mu, sd = x[est].mean(), x[est].std()
        years = sorted(g["year_eff"].unique().tolist())
        dummies = [(g["year_eff"] == yr).to_numpy(float) for yr in years[1:]]
        offset = x[list(fixed)].to_numpy(float) @ np.array([fixed[c][0] for c in fixed]) if fixed else np.zeros(len(g))
        X = np.column_stack([np.ones(len(g)), ((x[est] - mu) / sd).to_numpy(float)] + dummies)
        inv = np.linalg.pinv(X.T @ X)
        b = inv @ X.T @ (y - offset)
        e = y - offset - X @ b
        # 배 단위 군집 오차 (같은 배의 여러 해는 독립이 아니다)
        S = np.zeros((X.shape[1], X.shape[1]))
        for _, idx in pd.Series(np.arange(len(g))).groupby(g["imo"].to_numpy()):
            s = X[idx.to_numpy()].T @ e[idx.to_numpy()]
            S += np.outer(s, s)
        n_ship = g["imo"].nunique()
        V = inv @ S @ inv * n_ship / max(n_ship - 1, 1)
        # 표준화 전 단위로 되돌린 변수 계수와 공분산 (원인 분해에 쓴다)
        k = len(est)
        sdv = sd.to_numpy(float)
        coef = pd.concat([pd.Series(b[1 : 1 + k] / sdv, index=est), pd.Series({c: v[0] for c, v in fixed.items()}, dtype=float)])
        cov = pd.DataFrame(0.0, index=coef.index, columns=coef.index)
        cov.loc[est, est] = V[1 : 1 + k, 1 : 1 + k] / np.outer(sdv, sdv)
        for c, v in fixed.items():
            cov.loc[c, c] = v[1]
        yy = y - y.mean()
        return {
            "cols": est, "fixed": fixed, "mu": mu, "sd": sd, "years": years, "b": b, "coef": coef, "cov": cov,
            "r2": float(1 - (e @ e) / (yy @ yy)) if yy @ yy > 0 else float("nan"), "n": int(len(y)), "ships": int(n_ship),
            "resid_sd": float(np.sqrt(e @ e / max(len(y) - X.shape[1], 1))),
        }

    def _info(self, t: str, x: pd.DataFrame) -> dict:
        f = self.fits[t]
        elast = 0.0
        if SPEED_BASE in f["coef"].index:
            elast = float(f["coef"][SPEED_BASE])
            if f"{SPEED_BASE}^2" in f["coef"].index:
                elast += 2 * float(f["coef"][f"{SPEED_BASE}^2"]) * float(x[SPEED_BASE].median())
        return {"n": f["n"], "ships": f["ships"], "r2": round(f["r2"], 3), "speed_elasticity": round(elast, 3),
                "speed_is_wait": bool(elast <= self.params["elast_wait"]), "pooled": sorted(f["fixed"])}

    # ───────────────────────── 실행 ─────────────────────────
    def _predict(self, x: pd.DataFrame, year_eff: pd.Series, t: str) -> np.ndarray:
        f = self.fits[t]
        z = ((x[f["cols"]] - f["mu"]) / f["sd"]).to_numpy(float)
        ye = year_eff.to_numpy()
        d = [(ye == yr).astype(float) for yr in f["years"][1:]]
        pred = np.column_stack([np.ones(len(x)), z] + d) @ f["b"]
        if f["fixed"]:
            pred = pred + x[list(f["fixed"])].to_numpy(float) @ np.array([v[0] for v in f["fixed"].values()])
        return pred

    def _reference(self, df: pd.DataFrame) -> np.ndarray:
        ref = np.full((len(df), len(self.tokens)), np.nan)
        for i, (t, y, b) in enumerate(zip(df["ship_type"], df["year_eff"], df["size_bin"])):
            r = self.peer_ref.get((t, int(y), int(b)))
            ref[i] = r if r is not None else self.type_ref.get((t, int(b)), ref[i])
        return ref

    def _explain(self, df: pd.DataFrame, want_se: bool) -> tuple[pd.Series, pd.DataFrame, pd.DataFrame]:
        x = self._x(df)
        ref = pd.DataFrame(self._reference(df), index=df.index, columns=self.tokens)
        delta = (x - ref).where(ref.notna(), 0.0)
        ln_pred = pd.Series(0.0, index=df.index)
        contrib = pd.DataFrame(0.0, index=df.index, columns=list(self.groups))
        se = pd.DataFrame(0.0, index=df.index, columns=list(self.groups))
        for t, g in df.groupby("ship_type"):
            idx = g.index
            ln_pred.loc[idx] = self._predict(x.loc[idx], g["year_eff"], t)
            f = self.fits[t]
            for grp, toks in self.groups.items():
                cs = [c for c in toks if c in f["coef"].index]
                if not cs:
                    continue
                D = delta.loc[idx, cs].to_numpy(float)
                contrib.loc[idx, grp] = D @ f["coef"][cs].to_numpy(float)
                if want_se:
                    V = f["cov"].loc[cs, cs].to_numpy(float)
                    se.loc[idx, grp] = np.sqrt(np.einsum("ij,jk,ik->i", D, V, D).clip(min=0))
        return ln_pred, contrib, se

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        ln_pred, contrib, _ = self._explain(df, want_se=False)
        out = pd.DataFrame(0.0, index=df.index, columns=list(self.produces))
        out["sea_eff_expected"] = np.exp(ln_pred)
        for grp in self.groups:
            out[f"contrib_{grp}"] = contrib[grp]
        out["contrib_other"] = ln_pred - np.log(df["sea_eff_peer_median"]) - contrib.sum(axis=1)
        out["contrib_unexplained"] = np.log(df["sea_eff_kg_nm"]) - ln_pred
        return out

    # ───────────────────────── 화면·검토용 (결과 표 약속에는 없는 값) ─────────────────────────
    def cause_se(self, df: pd.DataFrame) -> pd.DataFrame:
        """원인 막대마다 오차 (배 단위 군집 오차). 화면에서 |기여| < 2×오차인 막대를 흐리게 그릴 때 쓴다."""
        _, _, se = self._explain(df, want_se=True)
        return se.add_prefix("se_")

    def coefficient_table(self) -> pd.DataFrame:
        """선종·변수별 계수, 군집 오차, t 값, 선종 간 공유 여부 (방현수 님 부호 검토용)."""
        rows = []
        for t, f in self.fits.items():
            for v in f["coef"].index:
                grp = next((g for g, toks in self.groups.items() if v in toks), "")
                se = float(np.sqrt(f["cov"].loc[v, v]))
                b = float(f["coef"][v])
                rows.append({"ship_type": t, "var": v, "group": grp, "coef": b, "se": se, "t": b / se if se else np.nan, "pooled": v in f["fixed"]})
        return pd.DataFrame(rows)
