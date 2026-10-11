"""5-2절 합격 기준 계산. python tasks.py evaluate → artifacts/<버전>/acceptance.{json,md}

모델 부품을 바꿔도 이 파일은 그대로 둔다. 기준값은 config/acceptance.yaml.
분리 원칙 (5-3절): 배 단위 교차 검증(같은 배는 한쪽에만), 시간 분할(과거로 학습·선정 → 미래로 확인).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import adjusted_rand_score
from sklearn.model_selection import GroupKFold

from models.bundle import ModelBundle
from shared.config import import_object


def _stage_index(specs: list[dict], column: str) -> int:
    for i, s in enumerate(specs):
        if column in import_object(s["use"]).produces:
            return i
    raise KeyError(f"{column} 을 만드는 부품이 설정에 없습니다")


def _r2(y: np.ndarray, p: np.ndarray) -> float:
    ok = np.isfinite(y) & np.isfinite(p)
    y, p = y[ok], p[ok]
    return float(1 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum())


# ① 같은 조건 기준: 처음 보는 배의 설명력 ─────────────────────────────────
def baseline_r2(df: pd.DataFrame, cfg: dict, acc: dict) -> dict[str, Any]:
    specs = cfg["stages"]
    k = _stage_index(specs, "sea_eff_expected")
    ref_specs = [dict(s) for s in specs[: k + 1]]
    ref_specs[k] = {**ref_specs[k], "params": {**ref_specs[k].get("params", {}), "features": acc["baseline"]["reference_features"]}}

    folds = GroupKFold(n_splits=acc["baseline"]["folds"])
    out = {"model": [], "reference": []}
    gaps = []
    for tr, te in folds.split(df, groups=df["imo"]):
        train, test = df.iloc[tr], df.iloc[te]
        for name, sp in (("model", specs[: k + 1]), ("reference", ref_specs)):
            b = ModelBundle.train(train, cfg, stage_specs=sp)
            w = b.run(test, validate=False)
            out[name].append(_r2(np.log(w["sea_eff_kg_nm"].to_numpy()), np.log(w["sea_eff_expected"].to_numpy())))
            if name == "model":
                gaps.append(w[["imo", "year", "contrib_unexplained"]])
    g = pd.concat(gaps).sort_values(["imo", "year"])
    g["prev"] = g.groupby("imo")["contrib_unexplained"].shift()
    yoy = float(g[["contrib_unexplained", "prev"]].dropna().corr().iloc[0, 1])
    r2m, r2r = float(np.mean(out["model"])), float(np.mean(out["reference"]))
    return {"r2_model": r2m, "r2_reference": r2r, "r2_gain": r2m - r2r, "gap_yoy_corr": yoy}


# ② 위치: 유지율 ───────────────────────────────────────────────────────────
def retention(df: pd.DataFrame, cfg: dict, acc: dict) -> dict[str, Any]:
    a = acc["position"]
    b = ModelBundle.train(df, cfg, cutoff_year=a["select_until"])
    res = b.run(df)
    piv = res.pivot_table(index="imo", columns="year", values="vs_expected_pct")
    years = [a["select_until"], *a["check_years"]]
    eligible = piv.dropna(subset=[y for y in years if y in piv.columns]).index
    if len(eligible) == 0 or any(y not in piv.columns for y in years):
        return {"error": "선정·확인 연도가 모두 있는 배가 없습니다"}

    def persisted(imos) -> float:
        if len(imos) == 0:
            return float("nan")
        v = piv.loc[imos, a["check_years"]]
        return float((v > a["persist_gap"] * 100).all(axis=1).mean())

    sel_rows = res[(res["year"] == a["select_until"]) & res["imo"].isin(eligible)]
    chosen = sel_rows.loc[sel_rows["position_class"] == "consistently_high", "imo"].to_numpy()

    sd = sel_rows.groupby("ship_type")["contrib_unexplained"].transform("std")
    z1 = sel_rows["contrib_unexplained"] / sd
    single = sel_rows.loc[z1 >= cfg["thresholds"]["z_consistently_high"], "imo"].to_numpy()

    rng = np.random.default_rng(cfg["train"]["seed"])
    n = max(len(chosen), 1)
    rand = float(np.mean([persisted(rng.choice(eligible, size=min(n, len(eligible)), replace=False)) for _ in range(200)]))
    r_model, r_single = persisted(chosen), persisted(single)
    return {
        "n_selected": int(len(chosen)), "n_single_year": int(len(single)), "n_eligible": int(len(eligible)),
        "retention_model": r_model, "retention_single_year": r_single, "retention_random": rand,
        "gain_vs_single_pp": (r_model - r_single) * 100 if np.isfinite(r_model) and np.isfinite(r_single) else float("nan"),
        "ratio_vs_random": r_model / rand if rand > 0 else float("nan"),
    }


# ③ 1~3년 예측 ─────────────────────────────────────────────────────────────
def forecast(df: pd.DataFrame, cfg: dict, acc: dict) -> dict[str, Any]:
    a = acc["forecast"]
    b = ModelBundle.train(df, cfg, cutoff_year=a["train_until"])
    res = b.run(df).set_index(["imo", "year"])
    base = res.xs(a["base_year"], level="year")
    errs_m, errs_p, cover = [], [], []
    for t in a["target_years"]:
        h = t - a["base_year"]
        actual = res.xs(t, level="year")["sea_eff_actual"]
        both = base.index.intersection(actual.index)
        y = actual.loc[both]
        errs_m.append((base.loc[both, f"fc_h{h}_p50"] - y).abs())
        errs_p.append((base.loc[both, "sea_eff_actual"] - y).abs())
        cover.append((y >= base.loc[both, f"fc_h{h}_p10"]) & (y <= base.loc[both, f"fc_h{h}_p90"]))
    mae_m, mae_p = float(pd.concat(errs_m).mean()), float(pd.concat(errs_p).mean())
    return {"mae_model": mae_m, "mae_persistence": mae_p, "mae_gain": 1 - mae_m / mae_p,
            "coverage_80": float(pd.concat(cover).mean()), "n": int(len(pd.concat(cover)))}


# ④ 유형 군집 안정성 ───────────────────────────────────────────────────────
def cluster_stability(df: pd.DataFrame, cfg: dict, acc: dict) -> dict[str, Any]:
    labels = []
    for seed in (cfg["train"]["seed"], cfg["train"]["seed"] + 1):
        c = {**cfg, "train": {**cfg["train"], "seed": seed}}
        labels.append(ModelBundle.train(df, c).run(df)[["type_exposure", "type_age_design"]])
    return {f"ari_{col}": float(adjusted_rand_score(labels[0][col].astype(int), labels[1][col].astype(int)))
            for col in ("type_exposure", "type_age_design")}


# 판정 ─────────────────────────────────────────────────────────────────────
def judge(m: dict, acc: dict) -> list[dict[str, Any]]:
    b, p, f, c = m["baseline"], m["position"], m["forecast"], m["cluster"]
    lo, hi = acc["forecast"]["coverage_range"]
    rows = [
        ("같은 조건: R² 향상", b["r2_gain"], f"≥ {acc['baseline']['min_r2_gain']}", b["r2_gain"] >= acc["baseline"]["min_r2_gain"]),
        ("위치: 유지율 − 한 해 기준 (%p)", p.get("gain_vs_single_pp"), f"≥ {acc['position']['min_gain_vs_single_pp']}",
         (p.get("gain_vs_single_pp") or -1e9) >= acc["position"]["min_gain_vs_single_pp"]),
        ("위치: 유지율 ÷ 무작위", p.get("ratio_vs_random"), f"≥ {acc['position']['min_ratio_vs_random']}",
         (p.get("ratio_vs_random") or -1e9) >= acc["position"]["min_ratio_vs_random"]),
        ("예측: MAE 개선률", f["mae_gain"], f"≥ {acc['forecast']['min_mae_gain']}", f["mae_gain"] >= acc["forecast"]["min_mae_gain"]),
        ("예측: 80% 구간 적중률", f["coverage_80"], f"{lo} ~ {hi}", lo <= f["coverage_80"] <= hi),
        ("유형: ARI (최소)", min(c.values()), f"≥ {acc['cluster']['min_ari']}", min(c.values()) >= acc["cluster"]["min_ari"]),
    ]
    return [{"criterion": n, "value": None if v is None or not np.isfinite(v) else round(float(v), 4), "threshold": t, "pass": bool(ok)}
            for n, v, t, ok in rows]


def evaluate(df: pd.DataFrame, cfg: dict, acc: dict, out_dir: Path) -> dict[str, Any]:
    metrics = {
        "baseline": baseline_r2(df, cfg, acc),
        "position": retention(df, cfg, acc),
        "forecast": forecast(df, cfg, acc),
        "cluster": cluster_stability(df, cfg, acc),
    }
    verdict = judge(metrics, acc)
    report = {"metrics": metrics, "verdict": verdict, "stages": cfg["stages"]}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "acceptance.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    md = ["| 기준 | 값 | 합격선 | 판정 |", "|---|---|---|---|"]
    md += [f"| {r['criterion']} | {r['value']} | {r['threshold']} | {'✅' if r['pass'] else '❌'} |" for r in verdict]
    (out_dir / "acceptance.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return report
