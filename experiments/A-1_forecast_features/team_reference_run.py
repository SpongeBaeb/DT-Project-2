"""팀 원본 코드(reg_common.py + 04_final_v4 셀 [1]·[2])를 그대로 실행해 기준 예측을 만든다 (재현 검증의 정답지).

    uv run python experiments/A-1_forecast_features/team_reference_run.py \
        --bundle <regression_v4_final_2026-10-12> --out <기준 CSV>

--bundle 폴더 안의 03_regression/reg_common.py, v1 피처 파일, mrv_pipeline 스냅샷(3183d290)을 쓴다. 팀 코드는 고치지 않는다.
출력은 imo + 기간별 med/s/q10/q90 (원본 forecast_v4.csv 의 같은 열). 모델 파일·그림은 저장하지 않는다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    reg = Path(a.bundle) / "03_regression"
    sys.path.insert(0, str(reg))
    import reg_common as rc                                  # 팀 코드 (mrv_reader 는 번들의 mrv_pipeline 에서 찾는다)

    feat, allf, df, cii = rc.load()
    HS, BASE = (1, 2, 3), 2025
    P = {h: rc.pairs_h(h, feat, allf, df, cii) for h in HS}
    feats = rc.NUM + rc.CAT
    X25 = allf[allf["year"] == BASE].copy().reset_index(drop=True).merge(
        cii[["imo", "year", "expd3", "ln_ar", "cii_rating", "cii_rating_2026basis", "cii_ship_type", "dwt", "gross_tonnage"]], on=["imo", "year"], how="left")
    X25["sea_bin"] = rc.sea_bin(X25["time_at_sea_h"])
    out = X25[["imo"]].copy()
    for h in HS:
        y, p = BASE + h, P[h]
        (Qc,) = rc.qfit(p[p["target_year"] <= BASE - 1], [p[p["target_year"] == BASE]])
        zq_raw = rc.w_ztable(Qc, p.loc[p["target_year"] == BASE, "delta"])
        Xh = X25.assign(covid_next=int(y in rc.COVID), target_year=y)
        (Q,) = rc.qfit(p[p["target_year"] <= BASE], [Xh])
        m, s, zq = rc.w_center(Q, zq_raw)
        out[f"med_{y}"], out[f"s_{y}"] = m, s
        out[f"q10_{y}"], out[f"q90_{y}"] = rc.w_q(zq, m, s, 0.10), rc.w_q(zq, m, s, 0.90)
        print(f"{y}: 학습 쌍 {int((p['target_year'] <= BASE).sum()):,}, 대표값 중앙값 {np.median(np.exp(m)) - 1:+.4%}")
    out.to_csv(a.out, index=False, encoding="utf-8-sig")
    print("저장:", a.out, out.shape, "/ 피처", len(feats))
    return 0


if __name__ == "__main__":
    sys.exit(main())
