"""선박 유형·이상 운항 (5-4절) — 팀 군집 노트북(차희성: 03~06, 최재희 님 두 축 유형 인수인계)을 Stage 로 옮긴 것.

두 부품이 임시 부품 TertileTypes 의 produces(type_exposure, type_age_design, ops_outlier)를 나눠 만든다.

TeamTypes — 팀 '두 축 유형' (선단 구성 요약, 05 노트북). 각 축은 변수 둘을 표준화해 K-평균(k=3, n_init=20)으로 나눈다.
  축 1 EU 규제 노출도   변수: 역내 항해 비중, ln(해상 시간)           1 역내 운항선 / 2 정기 기항선 / 3 비정기 기항선
  축 2 선령·설계 프로파일 변수: 선령 ÷ 통상 수명, 설계 효율 상대값 r_eff  1 고효율형 / 2 일반형 / 3 고선령형 (설계 효율 값이 없으면 빈칸)
  - 운항 값(역내 비중, 해상 시간)은 그 해까지 최근 3개 보고 연도의 중앙값 (한 해가 튀어도 흔들리지 않게). 2025년 행이면 팀의 2023~2025 중앙값과 같다.
  - 설계 효율 r_eff: (선종 × 지표 종류) 묶음마다 ln(값) = a + b·ln(크기) 의 잔차를 (값 − 중앙값) ÷ (IQR ÷ 1.349) 로, ±4 에서 자름. + = 나쁨.
    크기는 Ro-pax·크루즈선·자동차운반선은 총톤수, 나머지는 재화중량. 30척 미만 묶음은 선종 단위 회귀 계수를 쓴다.
  - 유형 번호: 노출도는 역내 비중 중심이 가장 높은 묶음 = 1, 남은 둘 중 해상 시간이 긴 쪽 = 2, 나머지 = 3.
              프로파일은 설계 효율 중심이 가장 좋은(낮은) 묶음 = 1, 남은 둘 중 선령이 높은 쪽 = 3, 나머지 = 2.
  - 소속 확률: exp(−거리² ÷ (2·s²)), s² = 자기 중심까지 거리² 평균 ÷ 변수 수 (묶음마다 퍼짐이 같다고 가정). 진짜 확률이 아니라 '중심에 가까운 정도'.
    가장 높은 확률이 0.6 미만이면 경계에 있는 배 (팀 기준).
  - 군집 중심·표준화·회귀 계수는 학습 데이터의 마지막 연도 선단(보고한 배 전체)으로 정해 저장한다 → 한 척만 넣어도 결과 표와 같은 유형.

OpsAnomaly — 이상 운항 (04 노트북). 선종마다 운항 지표 6개(EU 역내·출항·입항·정박 비중, ln 해상 시간, 선종·연도 중앙값 대비 속력)를
  0.5%·99.5% 로 자르고 표준화해 K-평균(k = min(6, 행수÷300))으로 요약하고, 가장 가까운 중심까지 거리(자르기 전 값 기준)가 선종 안 상위 2.5% 이면 ops_outlier.
  거리당 CO₂·잔차는 쓰지 않는다(검증에 쓸 지표라 넣으면 순환). 항해 유형 합이 안 맞는 행(co2_parts_bad)은 지표를 못 믿어 표시하지 않는다.
  이상 운항은 '더 쓰는 배'가 아니라 양쪽으로 크게 빗나가는 행이다 — 비효율 판단이 아니라 살펴볼 행의 표시.
  군집 중심·기준 거리는 학습 데이터 전체 행으로 정한다.

한계: 설계 효율 상대값과 유형은 그해 선단 기준이라, 선단이 바뀌면(새 연도) 같은 배의 유형이 바뀔 수 있다. 통상 수명은 가정값(냉동화물선·컨테이너·로로선 임시).
"""
from __future__ import annotations

import logging
import warnings

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

from models.base import FitContext, Stage

log = logging.getLogger("cluster")
MIN_PROFILE_SHIPS = 30                                   # 설계 효율 값이 있는 배가 이보다 적으면 선령·설계 유형을 만들지 않는다
# 선종별 통상 수명 (팀 가정값. 냉동화물선 25년·컨테이너·로로선 35년은 임시)
LIFESPAN = {
    "bulk": 25, "container": 25, "tanker": 25, "chemical_tanker": 25, "general_cargo": 25, "reefer": 25,
    "lng_carrier": 30, "gas_carrier": 30, "vehicle_carrier": 35, "ro_pax": 35, "ro_ro": 35, "cruise": 35, "container_ro_ro": 35,
}
GT_SIZE = ("ro_pax", "cruise", "vehicle_carrier")      # 크기를 총톤수로 보는 선종
DESIGN_KINDS = ("EEDI", "EEXI", "EIV")
MIN_GROUP = 30                                           # 이보다 적은 (선종, 지표 종류) 묶음은 선종 단위 회귀로 대신
EXPOSURE_NAMES = {1: "역내 운항선", 2: "정기 기항선", 3: "비정기 기항선"}
PROFILE_NAMES = {1: "고효율형", 2: "일반형", 3: "고선령형"}


def window_median(df: pd.DataFrame, col: str, window: int = 3) -> np.ndarray:
    """같은 배의 그 해까지 최근 `window` 개 달력 연도(해당 연도 보고가 있는 것만)의 중앙값. 미래 연도는 보지 않는다. df 의 (imo, year) 는 유일."""
    idx = pd.MultiIndex.from_arrays([df["imo"].to_numpy(), df["year"].to_numpy()])
    s = pd.Series(df[col].to_numpy(float), index=idx)
    cols = [s.reindex(pd.MultiIndex.from_arrays([df["imo"].to_numpy(), df["year"].to_numpy() - k])).to_numpy() for k in range(window)]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)       # 세 해가 모두 비면 NaN
        return np.nanmedian(np.column_stack(cols), axis=1)


def rel(v: pd.Series) -> tuple[float, float]:
    """상대값의 (중앙값, 퍼짐) — 퍼짐 = IQR ÷ 1.349. 퍼짐이 0 이면 상대값은 0."""
    q1, q3 = v.quantile(0.25), v.quantile(0.75)
    return float(v.median()), float((q3 - q1) / 1.349)


def apply_rel(v: np.ndarray, med: float, spread: float) -> np.ndarray:
    return np.clip((v - med) / spread, -4, 4) if spread > 0 else v * 0


def soft_membership(Z: np.ndarray, centers: np.ndarray, s2: float) -> tuple[np.ndarray, np.ndarray]:
    """(가장 가까운 중심 번호, 소속 확률 표). 소속 확률 = 정규화한 exp(−거리² ÷ (2·s²))."""
    D2 = ((Z[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
    W = np.exp(-D2 / (2 * s2))
    return D2.argmin(axis=1), W / W.sum(axis=1, keepdims=True)


class TeamTypes(Stage):
    requires = ("imo", "year", "year_eff", "ship_type", "eu_share", "sea_hours", "age", "dwt", "gt", "eedi", "eedi_kind")
    produces = ("type_exposure", "type_age_design", "type_exposure_prob", "type_age_design_prob")

    def __init__(self, k: int = 3, n_init: int = 20, window: int = 3, lifespan: dict[str, float] | None = None, **params):
        super().__init__(k=k, n_init=n_init, window=window, lifespan=lifespan, **params)
        self.k, self.n_init, self.window = int(k), int(n_init), int(window)
        self.lifespan = dict(lifespan or LIFESPAN)

    # ───────────────────────── 변수 ─────────────────────────
    def _basics(self, df: pd.DataFrame) -> pd.DataFrame:
        f = pd.DataFrame(index=df.index)
        eu = df["eu_share"].astype(float)
        if "co2_parts_bad" in df.columns:                     # 항해 유형 합이 안 맞는 행은 비중을 믿을 수 없어 비움 (팀 파이프라인과 같음)
            eu = eu.where(~df["co2_parts_bad"].astype(bool))
        f["t_intra"] = pd.Series(window_median(df.assign(_eu=eu), "_eu", self.window), index=df.index).fillna(0.0)
        f["t_sea"] = np.log(pd.Series(window_median(df, "sea_hours", self.window), index=df.index).where(lambda s: s > 0))
        f["t_age_life"] = df["age"].astype(float) / df["ship_type"].map(self.lifespan).astype(float)
        size = np.where(df["ship_type"].isin(GT_SIZE), df["gt"], df["dwt"]).astype(float)
        f["ls"] = np.log(pd.Series(size, index=df.index).where(lambda s: s > 0))
        e = df["eedi"].astype(float) if "eedi" in df.columns else pd.Series(np.nan, index=df.index)
        f["lv"] = np.log(e.where(e > 0))
        kind = df["eedi_kind"] if "eedi_kind" in df.columns else pd.Series(None, index=df.index, dtype=object)
        f["kind"] = kind.where(kind.isin(DESIGN_KINDS))
        return f

    def _r_eff(self, df: pd.DataFrame, f: pd.DataFrame) -> pd.Series:
        out = pd.Series(np.nan, index=df.index)
        for (t, k), idx in f.groupby([df["ship_type"], f["kind"]], observed=True).groups.items():
            p = self.design.get((t, k))
            ok = f.loc[idx, ["lv", "ls"]].notna().all(axis=1)
            if p is None or not ok.any():
                continue
            b0, b1, med, spread = p
            ii = ok[ok].index
            out.loc[ii] = apply_rel(f.loc[ii, "lv"].to_numpy() - (b0 + b1 * f.loc[ii, "ls"].to_numpy()), med, spread)
        return out

    # ───────────────────────── 학습 ─────────────────────────
    def fit(self, train: pd.DataFrame, ctx: FitContext) -> "TeamTypes":
        super().fit(train, ctx)
        df = train.sort_values(["imo", "year"], kind="mergesort")
        self.base_year = int(df["year"].max())
        f = self._basics(df)
        fleet = (df["year"] == self.base_year).to_numpy()
        # 설계 효율 회귀 (선종 × 지표 종류 묶음, 30척 미만은 선종 단위 회귀 계수)
        ok = f[["lv", "ls"]].notna().all(axis=1) & f["kind"].notna() & pd.Series(fleet, index=f.index)
        self.design: dict[tuple, tuple[float, float, float, float]] = {}
        for t, g in f[ok].groupby(df.loc[ok, "ship_type"]):
            def lsq(rows):
                A = np.column_stack([np.ones(len(rows)), f.loc[rows.index, "ls"].to_numpy()])
                return np.linalg.lstsq(A, f.loc[rows.index, "lv"].to_numpy(), rcond=None)[0]
            b_type = lsq(g)
            for k, gk in g.groupby(f.loc[g.index, "kind"]):
                b = lsq(gk) if len(gk) >= MIN_GROUP else b_type
                resid = f.loc[gk.index, "lv"] - (b[0] + b[1] * f.loc[gk.index, "ls"])
                med, spread = rel(resid)
                self.design[(t, k)] = (float(b[0]), float(b[1]), med, spread)
        f["r_eff"] = self._r_eff(df, f)
        # 축 1: 노출도
        X1 = f.loc[fleet, ["t_intra", "t_sea"]].dropna()
        if len(X1) < self.k:
            raise ValueError(f"{self.base_year}년 보고 선박이 {len(X1)}척뿐이라 노출도 유형 {self.k}개를 나눌 수 없습니다")
        self.ax1 = self._fit_axis(X1, ctx.seed)
        c = self.ax1["centers_raw"]
        o1 = int(np.argmax(c[:, 0]))
        rest = [i for i in range(self.k) if i != o1]
        o2 = max(rest, key=lambda i: c[i, 1])
        o3 = [i for i in rest if i != o2][0]
        self.ax1["order"] = {o1: 1, o2: 2, o3: 3}
        # 축 2: 선령·설계
        pp = f.loc[fleet, ["t_age_life", "r_eff"]].dropna()
        if len(pp) < max(self.k, MIN_PROFILE_SHIPS):                      # 설계 효율 값이 있는 배가 너무 적으면 이 축은 만들지 않는다 (유형은 빈칸)
            log.warning("설계 효율 값이 있는 배가 %d척뿐이라 선령·설계 유형을 만들지 않습니다", len(pp))
            self.ax2 = None
        else:
            self.ax2 = self._fit_axis(pp, ctx.seed)
            c = self.ax2["centers_raw"]
            q1 = int(np.argmin(c[:, 1]))
            rest = [i for i in range(self.k) if i != q1]
            q3 = max(rest, key=lambda i: c[i, 0])
            q2 = [i for i in rest if i != q3][0]
            self.ax2["order"] = {q1: 1, q2: 2, q3: 3}
        self.n_fleet = int(fleet.sum())
        return self

    def _fit_axis(self, X: pd.DataFrame, seed: int) -> dict:
        mu, sd = X.mean(), X.std(ddof=0)
        Z = ((X - mu) / sd).to_numpy()
        km = KMeans(n_clusters=self.k, n_init=self.n_init, random_state=int(seed)).fit(Z)
        D2 = ((Z[:, None, :] - km.cluster_centers_[None, :, :]) ** 2).sum(axis=2)
        s2 = float(D2[np.arange(len(Z)), km.labels_].mean() / Z.shape[1])          # 차원당 공통 분산
        return {"cols": list(X.columns), "mu": mu.to_numpy(), "sd": sd.to_numpy(), "centers": km.cluster_centers_, "s2": s2,
                "centers_raw": km.cluster_centers_ * sd.to_numpy() + mu.to_numpy()}

    # ───────────────────────── 실행 ─────────────────────────
    def _assign(self, ax: dict, X: pd.DataFrame, names: dict[int, int]) -> tuple[pd.Series, pd.Series]:
        lab = pd.Series(pd.NA, index=X.index, dtype="Int64")
        prob = pd.Series(np.nan, index=X.index)
        ok = X.notna().all(axis=1)
        if ok.any():
            Z = (X.loc[ok].to_numpy(float) - ax["mu"]) / ax["sd"]
            nearest, P = soft_membership(Z, ax["centers"], ax["s2"])
            lab.loc[ok] = pd.array([ax["order"][int(i)] for i in nearest], dtype="Int64")
            prob.loc[ok] = P.max(axis=1).round(3)
        return lab, prob

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        d = df.sort_values(["imo", "year"], kind="mergesort")
        f = self._basics(d)
        f["r_eff"] = self._r_eff(d, f)
        e, pe = self._assign(self.ax1, f[self.ax1["cols"]], self.ax1["order"])
        if self.ax2 is None:
            a, pa = pd.Series(pd.NA, index=f.index, dtype="Int64"), pd.Series(np.nan, index=f.index)
        else:
            a, pa = self._assign(self.ax2, f[self.ax2["cols"]], self.ax2["order"])
        out = pd.DataFrame({"type_exposure": e, "type_age_design": a, "type_exposure_prob": pe, "type_age_design_prob": pa}, index=d.index)
        return out.loc[df.index]

    def describe(self) -> dict:
        d = super().describe()
        d["detail"] = {"base_year": self.base_year, "fleet": self.n_fleet, "design_groups": len(self.design),
                       "exposure_centers": {EXPOSURE_NAMES[v]: [round(float(x), 3) for x in self.ax1["centers_raw"][i]] for i, v in self.ax1["order"].items()},
                       "profile_centers": ({PROFILE_NAMES[v]: [round(float(x), 3) for x in self.ax2["centers_raw"][i]] for i, v in self.ax2["order"].items()}
                                           if self.ax2 is not None else None)}
        return d


class OpsAnomaly(Stage):
    requires = ("imo", "year", "year_eff", "ship_type", "eu_share", "co2_t", "co2_from_eu_t", "co2_to_eu_t", "berth_share", "sea_hours",
                "avg_speed_kn", "co2_parts_bad")
    produces = ("ops_outlier",)
    FEATS = ["intra_eu_share", "from_eu_share", "to_eu_share", "berth_share", "ln_time", "rel_speed"]

    def __init__(self, k: int = 6, top: float = 0.025, rows_per_center: int = 300, n_init: int = 10, clip_q: float = 0.005, **params):
        super().__init__(k=k, top=top, rows_per_center=rows_per_center, n_init=n_init, clip_q=clip_q, **params)
        self.k, self.top, self.rows_per_center, self.n_init, self.clip_q = int(k), float(top), int(rows_per_center), int(n_init), float(clip_q)

    def _features(self, df: pd.DataFrame) -> pd.DataFrame:
        bad = df["co2_parts_bad"].astype(bool)
        co2 = df["co2_t"].astype(float)
        f = pd.DataFrame(index=df.index)
        f["intra_eu_share"] = df["eu_share"].astype(float).where(~bad)
        f["from_eu_share"] = (df["co2_from_eu_t"] / co2).clip(0, 1).where(~bad)
        f["to_eu_share"] = (df["co2_to_eu_t"] / co2).clip(0, 1).where(~bad)
        f["berth_share"] = df["berth_share"].astype(float).where(~bad)
        f["ln_time"] = np.log(df["sea_hours"].astype(float).where(lambda s: s > 0))
        ref = pd.Series([self.speed_med.get((t, int(y)), self.speed_med.get((t, None), np.nan)) for t, y in zip(df["ship_type"], df["year_eff"])], index=df.index)
        f["rel_speed"] = np.log(df["avg_speed_kn"].astype(float).where(lambda s: s > 0)) - np.log(ref)      # 선종·연도 중앙값 대비 (선종마다 설계 속력이 다르고 연도별로 전체가 움직임)
        return f

    def fit(self, train: pd.DataFrame, ctx: FitContext) -> "OpsAnomaly":
        super().fit(train, ctx)
        df = train.reset_index(drop=True)
        sp = df["avg_speed_kn"].astype(float).where(df["avg_speed_kn"] > 0)
        self.speed_med = {**sp.groupby([df["ship_type"], df["year_eff"]]).median().to_dict(), **{(t, None): v for t, v in sp.groupby(df["ship_type"]).median().items()}}
        f = self._features(df)
        usable = f.notna().all(axis=1)
        self.types: dict[str, dict] = {}
        for t, idx in f[usable].groupby(df.loc[usable, "ship_type"]).groups.items():
            X = f.loc[idx]
            lo, hi = X.quantile(self.clip_q), X.quantile(1 - self.clip_q)
            mu, sd = X.mean(), X.std(ddof=0)
            Z = (X.clip(lo, hi, axis=1) - mu) / sd                      # 군집은 자른 값으로, 거리는 자르기 전 값으로 (극단을 살림)
            km = KMeans(n_clusters=min(self.k, max(2, len(idx) // self.rows_per_center)), n_init=self.n_init, random_state=int(ctx.seed)).fit(Z)
            dist = self._dist(((X - mu) / sd).to_numpy(), km.cluster_centers_)
            self.types[t] = {"mu": mu.to_numpy(), "sd": sd.to_numpy(), "centers": km.cluster_centers_, "cut": float(np.quantile(dist, 1 - self.top)), "n": int(len(idx))}
        return self

    @staticmethod
    def _dist(Z: np.ndarray, centers: np.ndarray) -> np.ndarray:
        return np.sqrt(((Z[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)).min(axis=1)

    def score(self, df: pd.DataFrame) -> pd.Series:
        """가장 가까운 군집 중심까지 거리 (표준화 단위). 지표를 못 믿는 행·모르는 선종은 NaN."""
        f = self._features(df)
        score = pd.Series(np.nan, index=df.index)
        usable = f.notna().all(axis=1)
        for t, idx in f[usable].groupby(df.loc[usable, "ship_type"]).groups.items():
            p = self.types.get(t)
            if p is not None:
                score.loc[idx] = self._dist((f.loc[idx].to_numpy(float) - p["mu"]) / p["sd"], p["centers"])
        return score

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        score = self.score(df)
        cut = df["ship_type"].map({t: p["cut"] for t, p in self.types.items()}).astype(float)
        return pd.DataFrame({"ops_outlier": (score >= cut).fillna(False).astype(bool)}, index=df.index)

    def describe(self) -> dict:
        d = super().describe()
        d["detail"] = {"types": {t: {"rows": p["n"], "centers": int(len(p["centers"])), "cut": round(p["cut"], 3)} for t, p in self.types.items()}}
        return d
