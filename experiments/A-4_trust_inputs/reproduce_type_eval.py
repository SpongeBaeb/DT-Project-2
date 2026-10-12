"""팀 검증표 재현: evaluation/strict.py 가 팀 회귀 v4 의 type_eval_v4.csv(선종 × 기간 지표)와 test_metrics_v4.csv('엄격' 행)와 같은 숫자를 내는지 대조.

    uv run python experiments/A-4_trust_inputs/reproduce_type_eval.py \
        --merged <...>/mrv_merged_2026-10-06_3183d290.parquet --v4 <...>/03_regression/v4

구판 목표(정박 포함 거리당 CO₂)와 구판 스냅샷(3183d290)에서 돌린다. 신뢰 등급의 입력(과거 예측·지표)이 믿을 만한지 확인하는 단계다.
판정
  정확히 같아야 하는 값(모델이 개입하지 않음): 쌍, MAE 변화 없음, MAE 선형, 실제 D·E%, 상위10% 규칙
  LightGBM 잡음 안에서 같아야 하는 값: MAE v4, 치우침(선종 하나의 표준오차 약 0.004), 구간 포함률, D·E 예측−실제, 상위10% v4, 대비%
  절차: 팀의 '보정 연도를 따로 뗀' 시험 절차 (strict_predictions retrain=False)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evaluation.strict import overall_table, strict_predictions, type_table  # noqa: E402
from pipeline import mrv_source  # noqa: E402
from pipeline.run import Report  # noqa: E402
from shared.config import load_yaml  # noqa: E402
from shared.preprocess import derive, ensure_schema_columns  # noqa: E402

TYPES13 = ["container", "tanker", "chemical_tanker", "bulk", "general_cargo", "vehicle_carrier", "ro_pax", "gas_carrier",
           "lng_carrier", "ro_ro", "reefer", "cruise", "container_ro_ro"]
EXACT = {"쌍": 0.0, "연평균 척수": 0.0, "MAE 변화 없음": 1e-3, "MAE 선형": 2e-3, "실제 D·E%": 1e-6, "상위10% 규칙": 1e-6}
# 상위 10% 개수 처리는 표본이 아주 작은 행에서 한 쌍 차이를 만든다 (냉동화물선 3년 94쌍: 팀 값 80.0% 는 10개일 때만 가능, 반올림은 9개).
# 나머지 38행은 반올림으로 정확히 일치 → 이 열만 1행 허용
EXACT_ALLOW_ONE = {"상위10% 규칙"}
NOISY = {"MAE v4": 0.02, "치우침 2024": 0.02, "치우침 2025": 0.02, "구간 포함률%": 2.0, "D·E 예측−실제 %p": 2.0, "상위10% v4": 4.0, "변화 없음 대비%": 2.0, "선형 대비%": 2.0}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--merged", required=True)
    ap.add_argument("--v4", required=True)
    ap.add_argument("--rule", default="thr", choices=["thr", "nochange"])
    ap.add_argument("--out", default=None, help="재현한 선종 × 기간 표 CSV 저장 경로")
    ap.add_argument("--save-preds", default=None, help="엄격 검증 예측(배 × 시험) 저장 경로(.parquet)")
    a = ap.parse_args()
    colmap = load_yaml("config/column_map.yaml")
    raw = mrv_source.read_merged(Path(a.merged))
    d = derive(ensure_schema_columns(mrv_source.to_ship_year_input(raw, colmap, TYPES13, Report(), min_gt=5000)))
    inv = {}
    for eng, std in colmap["ship_types"].items():                              # 영문 이름이 여럿인 선종은 처음 나온 이름 (Oil tanker, Container ship, Bulk carrier, Ro-pax ship)
        if std in TYPES13:
            inv.setdefault(std, eng)
    d["ship_type"] = d["ship_type"].map(inv)                                    # 팀과 같은 영문 선종명 (범주 순서까지 같게)
    print(f"입력 {len(d):,}행 {d['imo'].nunique():,}척 → 엄격 검증 예측 생성 (시드 0)")
    preds = strict_predictions(d, "co2_per_nm_kg", seed=0, cii=True, verbose=True)
    if a.save_preds:
        preds.to_parquet(a.save_preds, index=False)
    mine = type_table(preds, rule=a.rule)
    if a.out:
        mine.to_csv(a.out, index=False, encoding="utf-8-sig")
    gold = pd.read_csv(Path(a.v4) / "type_eval_v4.csv", encoding="utf-8-sig")
    j = mine.merge(gold, on=["선종", "기간"], suffixes=("", "_팀"), validate="one_to_one")
    print(f"\n[선종 × 기간 표] 내 {len(mine)}행 / 팀 {len(gold)}행 / 맞춤 {len(j)}행")
    ok_all = True
    print("  — 정확히 같아야 하는 값 (모델이 개입하지 않음)")
    for c, tol in EXACT.items():
        diff = (j[c] - j[c + "_팀"]).abs()
        rel = diff / j[c + "_팀"].abs().clip(lower=1e-12)
        n_ok = int(((diff <= tol) | (rel <= tol)).sum()) if tol else int((diff == 0).sum())
        ok = n_ok == len(j) or (c in EXACT_ALLOW_ONE and n_ok >= len(j) - 1)
        ok_all &= ok
        print(f"    {c:12s} 최대 차이 {diff.max():.3g}  일치 {int(((diff <= tol) | (rel <= tol)).sum())}/{len(j)} {'✅' if ok else '❌'}")
    print("  — LightGBM 잡음 안에서 같아야 하는 값")
    for c, tol in NOISY.items():
        diff = (j[c] - j[c + "_팀"]).abs()
        within = diff <= (tol * j[c + "_팀"].abs().clip(lower=1e-9) if c == "MAE v4" else tol)
        n_ok = int(within.sum() + diff.isna().sum())
        print(f"    {c:12s} 평균 차이 {diff.mean():.3g} 최대 {diff.max():.3g}  허용 안 {n_ok}/{len(j)}")
        ok_all &= n_ok >= int(0.9 * len(j))
    gold_t = pd.read_csv(Path(a.v4) / "test_metrics_v4.csv", encoding="utf-8-sig")
    gold_t = gold_t[gold_t["protocol"] == "엄격"].rename(columns={"MAE 변화없음": "MAE 변화없음"})
    ov = overall_table(preds).merge(gold_t, on="h", suffixes=("", "_팀"))
    print("\n[기간별 전체 지표] (엄격)")
    for _, r in ov.iterrows():
        print(f"  h={int(r['h'])}: 쌍 {int(r['쌍'])}/{int(r['쌍_팀'])}  MAE v4 {r['MAE v4']:.4f}/{r['MAE v4_팀']:.4f}  선형 {r['MAE 선형']:.4f}/{r['MAE 선형_팀']:.4f}  변화없음 {r['MAE 변화없음']:.4f}/{r['MAE 변화없음_팀']:.4f}"
              f"  80% 포함 {r['80% 포함 v4']:.1f}/{r['80% 포함 v4_팀']:.1f}  치우침 {r['치우침 v4']:+.4f}/{r['치우침 v4_팀']:+.4f}  D·E AUC {r['D·E AUC v4']:.4f}/{r['D·E AUC v4_팀']:.4f}  상위200 {r['D·E 상위200 v4']:.1f}/{r['D·E 상위200 v4_팀']:.1f}")
        ok_all &= abs(r["MAE v4"] - r["MAE v4_팀"]) < 0.004 and r["쌍"] == r["쌍_팀"]
    print("\n결과:", "✅ 팀 검증표 재현" if ok_all else "❌ 차이가 있음 — 위 항목 확인")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
