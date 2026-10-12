"""신뢰 등급 입력 만들기: 새 스냅샷에서 '예측 시점에 아는 정보만 쓴' 과거 예측(엄격한 시간 분할)을 해상 효율·전체 효율 두 목표로 저장한다.

    uv run python experiments/A-4_trust_inputs/export_validation_predictions.py --config config/mrv_pipeline.yaml --out <폴더>

절차는 팀 회귀 v4 시험 절차와 같다 (evaluation/strict.py, retrain=False; 구판 목표에서 팀 type_eval_v4.csv 를 재현해 확인:
experiments/A-4_trust_inputs/reproduce_type_eval.py). 출발 연도 t 의 예측은 목표 연도 ≤ t−1 쌍으로 학습한 모델 하나로 보정(목표 연도 t 쌍의 오차)과 예측을 한다.
시험: 1년 뒤 = 출발 2023·2024, 2년 뒤 = 출발 2022·2023, 3년 뒤 = 출발 2022 (목표 연도 2024·2025)

출력 (--out 폴더)
  검증예측_해상효율.csv / .parquet   배 × 시험 한 줄 (정박 제외 해상 효율 목표)
  검증예측_전체효율.csv / .parquet   같은 형식 + CII D·E 확률과 실제 D·E (정박 포함 거리당 CO₂ 목표)
  지표표_해상효율.csv, 지표표_전체효율.csv   선종 × 기간 지표표 (팀 type_eval_v4.csv 와 같은 열, 등급 열 제외)
  기간별_전체지표_*.csv              기간별 전체 지표
  설명.md                            열 설명
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evaluation.strict import QUANTILE_LEVELS, overall_table, strict_predictions, type_table  # noqa: E402
from pipeline.run import load_snapshot  # noqa: E402
from shared.config import load_config  # noqa: E402

TARGETS = {
    "해상효율": {"level": "sea_eff_kg_nm", "cii": False, "label": "해상 효율 (정박 제외, kg CO₂/해리)"},
    "전체효율": {"level": "co2_per_nm_kg", "cii": True, "label": "전체 효율 (정박 포함 거리당 CO₂, kg CO₂/해리)"},
}
TYPE_KO = {
    "container": "컨테이너선", "tanker": "유조선", "bulk": "벌크선", "chemical_tanker": "화학제품운반선", "general_cargo": "일반화물선",
    "vehicle_carrier": "자동차운반선", "ro_pax": "로팩스", "gas_carrier": "가스운반선", "lng_carrier": "LNG선", "ro_ro": "로로선",
    "reefer": "냉동화물선", "cruise": "크루즈선", "container_ro_ro": "컨테이너·로로선",
}


def decorate(preds: pd.DataFrame, names: pd.Series) -> pd.DataFrame:
    p = preds.copy()
    p.insert(1, "선박명", p["imo"].map(names))
    p.insert(3, "선종_한글", p["ship_type"].map(TYPE_KO))
    for q in (10, 50, 90):                                                    # 변화(로그)를 수준(kg/해리)으로도: 실제와 바로 비교할 수 있게
        p[f"예측_p{q}"] = p["level_t"] * np.exp(p["m" if q == 50 else f"q{q}"])
    p = p.rename(columns={"t": "출발연도", "h": "기간_년", "target_year": "목표연도", "level_t": "출발연도_수준", "level_target": "목표연도_실제수준",
                          "delta": "실제변화_ln", "m": "대표값_변화_ln", "s": "폭_s"})
    return p


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="config/mrv_pipeline.yaml")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    df = load_snapshot(load_config(a.config)).sort_values(["imo", "year"]).reset_index(drop=True)
    names = df.sort_values("year").groupby("imo")["name"].last()
    print(f"스냅샷 {len(df):,}행 {df['imo'].nunique():,}척, 시드 {a.seed}", flush=True)
    for key, spec in TARGETS.items():
        print(f"\n[{key}] {spec['label']}", flush=True)
        preds = strict_predictions(df, spec["level"], seed=a.seed, cii=spec["cii"], verbose=True)
        full = decorate(preds, names)
        full.to_csv(out / f"검증예측_{key}.csv", index=False, encoding="utf-8-sig")
        full.to_parquet(out / f"검증예측_{key}.parquet", index=False)
        type_table(preds).to_csv(out / f"지표표_{key}.csv", index=False, encoding="utf-8-sig")
        ov = overall_table(preds)
        ov.to_csv(out / f"기간별_전체지표_{key}.csv", index=False, encoding="utf-8-sig")
        print(ov[["h", "쌍", "MAE v4", "MAE 선형", "MAE 변화없음", "80% 포함 v4", "치우침 v4"]].round(4).to_string(index=False), flush=True)
    (out / "설명.md").write_text(DESC, encoding="utf-8")
    print("\n저장:", out)
    return 0


DESC = """# 검증 예측 (신뢰 등급 입력)

예측 시점에 아는 정보만으로 만든 과거 예측과 실제를 배 × 시험 한 줄로 저장한 파일입니다.

## 절차
- 팀 회귀 v4 의 시험 절차와 같습니다 (구판 목표에서 팀 `type_eval_v4.csv` 를 재현해 확인).
- 출발 연도 t 의 예측: 목표 연도 ≤ t−1 쌍으로 학습한 모델 하나로 (1) 목표 연도 t 쌍의 오차 → 보정(z 표), (2) 출발 연도 t 의 배들 예측. 보정 연도를 학습에서 뗀 절차라 운영 모델보다 학습 쌍이 적어 성적이 보수적입니다.
- 시험: 1년 뒤 = 출발 2023·2024, 2년 뒤 = 출발 2022·2023, 3년 뒤 = 출발 2022 (목표 연도 2024·2025).
- 모델: LightGBM 분위수 7개 + 배별 폭 + 중심 보정, 시드 0. 재학습하면 지표가 평균 3e-3 정도 달라지는 잡음이 있습니다.

## 열
| 열 | 뜻 |
|---|---|
| `imo`, `선박명`, `ship_type`, `선종_한글` | 선박 식별 |
| `기간_년`, `출발연도`, `목표연도` | 몇 년 뒤 예측인지, 예측을 낸 해, 맞춘 해 |
| `출발연도_수준`, `목표연도_실제수준` | 출발·목표 연도의 실제 값 (kg CO₂/해리) |
| `실제변화_ln` | ln(목표 연도 실제 ÷ 출발 연도 실제) = 맞춰야 할 값 |
| `대표값_변화_ln`, `폭_s` | 예측 대표값(중앙값)과 배별 폭 |
| `q5` … `q95` | 예측 분위 (로그 변화 단위) |
| `예측_p10`, `예측_p50`, `예측_p90` | 같은 분위를 수준(kg CO₂/해리)으로 바꾼 값 = 출발연도_수준 × exp(q) |
| `pred_linear` | 평균 회귀 선형 기준의 예측 (비교 기준) |
| `thr_de`, `p_de`, `p_de_nochange`, `de_target` | (전체 효율 파일만) D·E 임계값, 예측 D·E 확률, 변화를 0 으로 둔 확률, 목표 연도 실제 D·E(1/0, 등급이 없으면 빈칸) |
| `level` | 목표 지표 (`sea_eff_kg_nm` 해상 효율 / `co2_per_nm_kg` 정박 포함 거리당 CO₂) |

## 지표를 만드는 법 (팀 type_eval_v4.csv 와 같음)
- MAE = 평균 |실제변화_ln − 대표값_변화_ln|, 변화 없음 MAE = 평균 |실제변화_ln|, 선형 MAE = 평균 |실제변화_ln − pred_linear|
- 치우침 = 평균(실제변화_ln − 대표값_변화_ln) (목표 연도별), 구간 포함률 = 실제변화_ln 이 q10~q90 안인 비율
- D·E 상위 10% = 점수 상위 10%(반올림) 중 실제 D·E 비율. 규칙 점수 = −thr_de (현재 수준), v4 점수 = p_de
- 선종 × 기간으로 묶고 두 시험 연도를 합쳐 셉니다. 해상 효율 파일에는 D·E 열이 없습니다 (CII 는 정박 포함 총량 기준).
"""

if __name__ == "__main__":
    sys.exit(main())
