"""정박 몫(kg CO₂/해리 = 총 − 해상) 기준선 비교: 학습 없이 '예년 수준' 방식들이 얼마나 맞는지.

    uv run python experiments/A-5_berth/baselines.py --val "<검증예측 폴더>" --out <결과 폴더>

쌍 집합은 검증예측(해상·전체 효율 모두 있는 쌍, evaluation/strict.py 의 시험)과 같다. 예측은 출발 연도 t 까지의 정보만 쓴다.
기준선: last(마지막 값) / mean3 / median3(최근 3년) / shrink(그 배 최근 3년 평균을 같은 선종·연도 평균 쪽으로 당김) / type(선종·연도 평균) / implied(총예측−해상예측 중앙값)
수축 계수 k 는 시험 이전 출발 연도(2020·2021, h=1)의 쌍으로 고른다 (시험 쌍에서 고르지 않음).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline.run import load_snapshot  # noqa: E402
from shared.config import load_config  # noqa: E402

KS = (0.5, 1, 2, 4, 8)


def berth_table(df: pd.DataFrame) -> pd.DataFrame:
    d = df[["imo", "year", "ship_type", "co2_per_nm_kg", "sea_eff_kg_nm"]].copy()
    d["berth"] = d["co2_per_nm_kg"] - d["sea_eff_kg_nm"]
    return d


def baselines_at(d: pd.DataFrame, t: int, imos: pd.Series, k_list=KS) -> pd.DataFrame:
    """출발 연도 t 에서 imos 의 기준선 예측 (t 까지의 행만 사용)."""
    hist = d[d["year"] <= t]
    w3 = hist[hist["year"] >= t - 2]
    g = w3.groupby("imo")["berth"]
    cur = hist[hist["year"] == t].set_index("imo")
    tm = cur.groupby("ship_type")["berth"].mean()                                   # 같은 선종·연도 평균
    out = pd.DataFrame({"imo": imos.to_numpy()}).set_index("imo")
    out["last"] = cur["berth"].reindex(out.index)
    out["mean3"] = g.mean().reindex(out.index)
    out["median3"] = g.median().reindex(out.index)
    n = g.size().reindex(out.index)
    st = cur["ship_type"].reindex(out.index).map(tm)
    out["type"] = st
    for k in k_list:
        out[f"shrink_k{k}"] = (n * out["mean3"] + k * st) / (n + k)
    return out.reset_index()


def metrics(pred: pd.Series, actual: pd.Series) -> dict:
    e = actual - pred
    ok = e.notna()
    return {"n": int(ok.sum()), "MAE": float(e[ok].abs().mean()), "중앙 오차": float(e[ok].median()), "평균 오차": float(e[ok].mean()),
            "상관": float(np.corrcoef(pred[ok], actual[ok])[0, 1])}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="config/mrv_pipeline.yaml")
    ap.add_argument("--val", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    d = berth_table(load_snapshot(load_config(a.config)))
    act = d.set_index(["imo", "year"])["berth"]
    key = ["imo", "기간_년", "출발연도"]
    tot, sea = (pd.read_parquet(Path(a.val) / f"검증예측_{n}.parquet") for n in ("전체효율", "해상효율"))
    v = tot[key + ["ship_type", "목표연도", "예측_p50"]].merge(sea[key + ["예측_p50"]], on=key, suffixes=("_tot", "_sea"))
    v["implied"] = v["예측_p50_tot"] - v["예측_p50_sea"]
    print(f"쌍 {len(v):,} (정박분 0: 실제 {int((act.reindex(pd.MultiIndex.from_arrays([v['imo'], v['목표연도']])).to_numpy() == 0).sum()):,}쌍)", flush=True)

    # 수축 계수 선택: 시험 이전 출발 연도의 쌍 (h=1, t=2020·2021)
    sel = []
    for t in (2020, 2021):
        ships = d[(d["year"] == t)]["imo"]
        b = baselines_at(d, t, ships)
        b["actual"] = act.reindex(pd.MultiIndex.from_arrays([b["imo"], np.full(len(b), t + 1)])).to_numpy()
        sel.append(b)
    sel = pd.concat(sel)
    ktab = pd.DataFrame({f"shrink_k{k}": metrics(sel[f"shrink_k{k}"], sel["actual"]) for k in KS}).T
    print("\n수축 계수 선택 (h=1, 출발 2020·2021):\n", ktab[["n", "MAE"]].round(3).to_string(), flush=True)
    kbest = min(KS, key=lambda k: ktab.loc[f"shrink_k{k}", "MAE"])
    print("선택 k =", kbest, flush=True)

    rows, parts = [], []
    for (h, t), g in v.groupby(["기간_년", "출발연도"]):
        b = baselines_at(d, int(t), g["imo"])
        g = g.merge(b, on="imo", how="left")
        parts.append(g)
    P = pd.concat(parts, ignore_index=True)
    P["actual"] = act.reindex(pd.MultiIndex.from_arrays([P["imo"], P["목표연도"]])).to_numpy()
    P["shrink"] = P[f"shrink_k{kbest}"]
    methods = ["last", "mean3", "median3", "shrink", "type", "implied"]
    res = []
    for h, g in P.groupby("기간_년"):
        ok = g[methods + ["actual"]].notna().all(axis=1)                          # 모든 방식이 값을 낼 수 있는 쌍으로 맞춤
        gg = g[ok]
        for m in methods:
            res.append({"기간": h, "방식": m, **metrics(gg[m], gg["actual"])})
    R = pd.DataFrame(res)
    print("\n기간별 (모든 방식이 값을 내는 쌍):\n", R.round(3).to_string(index=False), flush=True)
    R.to_csv(out / "정박_기준선_기간별.csv", index=False, encoding="utf-8-sig")

    gg = P[P[methods + ["actual"]].notna().all(axis=1)]
    t1 = []
    for (st, h), g in gg.groupby(["ship_type", "기간_년"]):
        if h != 1 or len(g) < 100:
            continue
        t1.append({"선종": st, "쌍": len(g), "정박분 중앙값": g["actual"].median(), **{f"MAE {m}": (g["actual"] - g[m]).abs().mean() for m in methods}})
    T = pd.DataFrame(t1).sort_values("쌍", ascending=False)
    print("\n선종별 h=1 (쌍 100 이상):\n", T.round(2).to_string(index=False), flush=True)
    T.to_csv(out / "정박_기준선_선종별_h1.csv", index=False, encoding="utf-8-sig")
    ktab.to_csv(out / "정박_수축계수_선택.csv", encoding="utf-8-sig")
    return 0


if __name__ == "__main__":
    sys.exit(main())
