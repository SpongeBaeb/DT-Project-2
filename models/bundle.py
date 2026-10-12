"""모델 묶음: 설정에 적힌 부품들을 순서대로 학습·실행하고 결과 표(RESULT_TABLE)를 만든다.

결과 표(배치)와 진단 API(한 척)는 둘 다 ModelBundle.run() 하나를 부른다 → 같은 계산이 보장된다.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from contracts.tables import CONTRIB_COLS, P_DE_COLS, RESULT_TABLE, SHIP_YEAR, TOTAL_FORECAST_COLS
from models.base import FitContext, Stage
from shared.config import import_object
from shared.manifest import frame_hash, now_iso

IDENTITY_TOL = 1e-9
BUNDLE_COLS = {"sea_eff_actual", "berth_actual_t", "vs_peer_pct", "vs_expected_pct", "warnings"}  # 묶음이 직접 채우는 열
OPTIONAL_COLS = set(TOTAL_FORECAST_COLS) | set(P_DE_COLS)       # 이 열을 만드는 부품이 없으면 빈칸으로 둔다 (결과 표 2.1·2.2 의 선택 열)
RANGE_FEATURES = ("ln_dwt", "avg_speed_kn", "ln_sea_hours", "age", "berth_share", "eu_share")


class ModelBundle:
    def __init__(self, stages: list[Stage], meta: dict[str, Any]):
        self.stages = stages
        self.meta = meta

    # ───────────────────────────── 학습 ─────────────────────────────
    @classmethod
    def train(
        cls,
        ship_year: pd.DataFrame,
        config: dict[str, Any],
        *,
        cutoff_year: int | None = None,
        stage_specs: list[dict[str, Any]] | None = None,
        until_stage: int | None = None,
    ) -> "ModelBundle":
        """until_stage: 앞에서부터 이 개수의 부품만 학습 (비교 실험용). None = 전부."""
        df = SHIP_YEAR.validate(ship_year).sort_values(["imo", "year"], kind="mergesort").reset_index(drop=True)
        cutoff = cutoff_year if cutoff_year is not None else config["train"].get("cutoff_year")
        train_mask = df["year"] <= cutoff if cutoff is not None else pd.Series(True, index=df.index)
        train_years = sorted(df.loc[train_mask, "year"].unique().tolist())
        if not train_years:
            raise ValueError(f"학습할 행이 없습니다 (cutoff_year={cutoff})")

        ctx = FitContext(cutoff_year=cutoff, seed=config["train"]["seed"], thresholds=config["thresholds"], config=config)
        specs = list(stage_specs if stage_specs is not None else config["stages"])[:until_stage]

        work = _with_year_eff(df, train_years)
        stages: list[Stage] = []
        for spec in specs:
            stage = import_object(spec["use"])(**spec.get("params", {}))
            _check_requires(stage, work)
            stage.fit(work.loc[train_mask].copy(), ctx)
            work = _merge(work, _checked_output(stage, work))
            stages.append(stage)

        train = df.loc[train_mask]
        q_lo, q_hi = config["thresholds"]["train_range_q"]
        ranges = {
            t: {f: [float(g[f].quantile(q_lo)), float(g[f].quantile(q_hi))] for f in RANGE_FEATURES if g[f].notna().any()}
            for t, g in train.groupby("ship_type")
        }
        meta = {
            "model_version": f"{config['project']['model_version']}+{frame_hash(train)[:8]}",
            "data_hash": frame_hash(df),
            "train_data_hash": frame_hash(train),
            "result_table_version": RESULT_TABLE.version,
            "cutoff_year": cutoff,
            "train_years": train_years,
            "ship_types": sorted(train["ship_type"].unique().tolist()),
            "ranges": ranges,
            "stages": [s.describe() for s in stages],
            # 부품 일부만 학습한 묶음(비교 실험용)이면 run() 은 결과 표 대신 중간 표를 돌려준다
            "complete": set(RESULT_TABLE.names) - BUNDLE_COLS - OPTIONAL_COLS <= set(work.columns),
            "created_at": now_iso(),
        }
        return cls(stages, meta)

    # ───────────────────────────── 실행 ─────────────────────────────
    def run(self, ship_year: pd.DataFrame, *, validate: bool = True) -> pd.DataFrame:
        """SHIP_YEAR 모양의 행들 → 결과 표. 행 순서는 (imo, year)."""
        df = SHIP_YEAR.validate(ship_year).sort_values(["imo", "year"], kind="mergesort").reset_index(drop=True)
        unknown = sorted(set(df["ship_type"]) - set(self.meta["ship_types"]))
        if unknown:
            raise ValueError(f"학습에 없는 선종: {unknown} (가능: {self.meta['ship_types']})")

        work = _with_year_eff(df, self.meta["train_years"])
        for stage in self.stages:
            work = _merge(work, _checked_output(stage, work))
        if not self.meta.get("complete", True):
            return work

        for c in OPTIONAL_COLS - set(work.columns):
            work[c] = np.nan
        work["sea_eff_actual"] = work["sea_eff_kg_nm"]
        work["berth_actual_t"] = work["berth_co2_t"]
        work["vs_peer_pct"] = (work["sea_eff_actual"] / work["sea_eff_peer_median"] - 1) * 100
        work["vs_expected_pct"] = (work["sea_eff_actual"] / work["sea_eff_expected"] - 1) * 100
        work["warnings"] = self._warnings(work)

        out = RESULT_TABLE.validate(work[RESULT_TABLE.names], extra="forbid") if validate else work[RESULT_TABLE.names]
        _check_identity(out)
        return out

    def _warnings(self, work: pd.DataFrame) -> pd.Series:
        last = max(self.meta["train_years"])
        msgs: list[list[str]] = [[] for _ in range(len(work))]
        for i, (year, t) in enumerate(zip(work["year"], work["ship_type"])):
            if year > last:
                msgs[i].append(f"학습 연도 밖: 연도 효과는 {last}년 값 사용")
        for f in RANGE_FEATURES:
            v = work[f].to_numpy(dtype=float)
            for i, t in enumerate(work["ship_type"]):
                lo_hi = self.meta["ranges"].get(t, {}).get(f)
                if lo_hi and np.isfinite(v[i]) and not (lo_hi[0] <= v[i] <= lo_hi[1]):
                    msgs[i].append(f"학습 범위 밖(외삽): {f}={v[i]:.4g} (선종 1~99%: {lo_hi[0]:.4g}~{lo_hi[1]:.4g})")
        return pd.Series([" | ".join(m) for m in msgs], index=work.index, dtype=object)

    # ───────────────────────────── 저장 ─────────────────────────────
    def save(self, directory: str | Path) -> Path:
        d = Path(directory)
        d.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, d / "model.joblib", compress=3)
        (d / "model_meta.json").write_text(json.dumps(self.meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return d / "model.joblib"

    @staticmethod
    def load(directory: str | Path) -> "ModelBundle":
        b = joblib.load(Path(directory) / "model.joblib")
        if not isinstance(b, ModelBundle):
            raise TypeError("model.joblib 이 ModelBundle 이 아닙니다")
        return b


# ───────────────────────────── 내부 도구 ─────────────────────────────
def _with_year_eff(df: pd.DataFrame, train_years: list[int]) -> pd.DataFrame:
    out = df.copy()
    out["year_eff"] = out["year"].clip(lower=min(train_years), upper=max(train_years)).astype("int64")
    return out


def _check_requires(stage: Stage, work: pd.DataFrame) -> None:
    missing = [c for c in stage.requires if c not in work.columns]
    if missing:
        raise KeyError(f"{stage.name} 에 필요한 열이 없습니다: {missing}. 설정의 부품 순서를 확인하세요.")


def _checked_output(stage: Stage, work: pd.DataFrame) -> pd.DataFrame:
    _check_requires(stage, work)
    out = stage.transform(work)
    if not isinstance(out, pd.DataFrame):
        raise TypeError(f"{stage.name}.transform() 은 DataFrame 을 돌려줘야 합니다")
    if list(out.columns) != list(stage.produces) and set(out.columns) != set(stage.produces):
        raise KeyError(f"{stage.name}: produces={stage.produces} 인데 실제 {list(out.columns)}")
    if not out.index.equals(work.index):
        raise ValueError(f"{stage.name}: transform 결과의 index 가 입력과 다릅니다 (행 순서·개수 유지 필요)")
    return out[list(stage.produces)]


def _merge(work: pd.DataFrame, out: pd.DataFrame) -> pd.DataFrame:
    return pd.concat([work.drop(columns=[c for c in out.columns if c in work.columns]), out], axis=1)


def _check_identity(res: pd.DataFrame) -> None:
    """약속: 원인 막대 합 == ln(실제/동급 중간)."""
    total = res[CONTRIB_COLS].sum(axis=1)
    target = np.log(res["sea_eff_actual"] / res["sea_eff_peer_median"])
    err = float((total - target).abs().max()) if len(res) else 0.0
    if err > IDENTITY_TOL:
        raise ValueError(f"원인 막대 합 ≠ 동급 대비 차이 (최대 오차 {err:.3g})")
