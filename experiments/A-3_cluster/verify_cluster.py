"""군집 Stage 이식 검증: models/cluster/team.py 가 팀 군집 노트북(05 두 축 유형, 04 이상 운항)의 결과 메모와 같은 숫자를 내는지 대조.

    uv run python experiments/A-3_cluster/verify_cluster.py \
        --merged <regression_v4_final>/mrv_pipeline/data/processed/snapshots/mrv_merged_2026-10-06_3183d290.parquet

팀 노트북은 2024년분 v247·2025년분 v60 (= 이 스냅샷 3183d290) 위에서 돌렸다. 정답으로 쓰는 숫자 (노트북 '확인 메모'):
  05 두 축 유형 (총톤수 5,000 이상 2025년 보고 12,663척):
     노출도 역내/정기/비정기 = 1,800 / 5,880 / 4,983, 프로파일 고효율/일반/고선령/없음 = 2,088 / 5,055 / 5,258 / 262,
     경계(소속 확률 0.6 미만) 노출도 5.7%, 프로파일 16.1%
  04 이상 운항 (모든 행 96,382, 지표가 모두 있는 96,138행): 이상 운항 2,410행(2.51%), 2,004척, 선종별 거리 기준 2.96~4.56
K-평균 시드는 팀 노트북과 같게 0 으로 둔다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from models.base import FitContext  # noqa: E402
from models.cluster.team import OpsAnomaly, TeamTypes  # noqa: E402
from pipeline import mrv_source  # noqa: E402
from pipeline.run import Report  # noqa: E402
from shared.config import load_yaml  # noqa: E402
from shared.preprocess import derive, ensure_schema_columns  # noqa: E402

TYPES13 = ["container", "tanker", "chemical_tanker", "bulk", "general_cargo", "vehicle_carrier", "ro_pax", "gas_carrier",
           "lng_carrier", "ro_ro", "reefer", "cruise", "container_ro_ro"]
TEAM_05 = {"expo": (1800, 5880, 4983), "prof": (2088, 5055, 5258, 262), "border": (0.057, 0.161)}
TEAM_04 = {"rows": 2410, "ships": 2004, "usable": 96138, "cut": (2.96, 4.56)}


def close(a, b, tol):
    return abs(a - b) <= tol * max(abs(b), 1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--merged", required=True)
    a = ap.parse_args()
    ctx = FitContext(cutoff_year=None, seed=0, thresholds={})
    colmap = load_yaml("config/column_map.yaml")
    raw = mrv_source.read_merged(Path(a.merged))
    allrows = derive(ensure_schema_columns(mrv_source.to_ship_year_input(raw, colmap, TYPES13, Report(), min_gt=None)))
    allrows["year_eff"] = allrows["year"]
    big = allrows[allrows["gt"] >= 5000].reset_index(drop=True)                    # 팀 공통 범위
    ok = True

    print(f"[05 두 축 유형] 학습 {len(big):,}행 (총톤수 5,000 이상), 2025년 보고 {int((big['year'] == 2025).sum()):,}척")
    st = TeamTypes().fit(big, ctx)
    y25 = big[big["year"] == 2025]
    out = st.transform(big).loc[y25.index]
    e = out["type_exposure"].value_counts().reindex([1, 2, 3]).fillna(0).astype(int).tolist()
    p = out["type_age_design"].value_counts().reindex([1, 2, 3]).fillna(0).astype(int).tolist() + [int(out["type_age_design"].isna().sum())]
    bd = (float((out["type_exposure_prob"] < 0.6).mean()), float((out["type_age_design_prob"] < 0.6).mean()))     # 팀과 같게: 유형이 없는 배도 분모에 포함
    print(f"  노출도 역내/정기/비정기  내 {tuple(e)}  팀 {TEAM_05['expo']}")
    print(f"  프로파일 고효율/일반/고선령/없음  내 {tuple(p)}  팀 {TEAM_05['prof']}")
    print(f"  경계(확률 0.6 미만) 노출도/프로파일  내 {bd[0]:.3f} / {bd[1]:.3f}  팀 {TEAM_05['border'][0]} / {TEAM_05['border'][1]}")
    ok_e = all(close(x, y, 0.02) for x, y in zip(e, TEAM_05["expo"]))
    ok_p = all(close(x, y, 0.03) for x, y in zip(p, TEAM_05["prof"]))
    ok_b = abs(bd[0] - TEAM_05["border"][0]) < 0.002 and abs(bd[1] - TEAM_05["border"][1]) < 0.002
    print("  노출도", "✅" if ok_e else "❌", "프로파일", "✅" if ok_p else "❌", "경계 비율", "✅" if ok_b else "❌")
    # 한 척 = 전체
    some = y25["imo"].drop_duplicates().sample(25, random_state=1)
    alone = pd.concat([st.transform(big[big["imo"] == i]) for i in some])
    full = st.transform(big).loc[alone.index]
    same = alone.equals(full)
    print("  한 척 입력 = 전체 결과:", "✅" if same else "❌")
    ok &= ok_e and ok_p and ok_b and same

    print(f"\n[04 이상 운항] 학습 {len(allrows):,}행 (모든 총톤수)")
    op = OpsAnomaly().fit(allrows, ctx)
    score = op.score(allrows)
    flag = op.transform(allrows)["ops_outlier"]
    usable = int(score.notna().sum())
    rows, ships = int(flag.sum()), int(allrows.loc[flag, "imo"].nunique())
    cuts = [p_["cut"] for p_ in op.types.values()]
    print(f"  지표가 모두 있는 행  내 {usable:,}  팀 {TEAM_04['usable']:,}")
    print(f"  이상 운항 행/척  내 {rows:,} ({rows / usable:.2%}) / {ships:,}  팀 {TEAM_04['rows']:,} (2.51%) / {TEAM_04['ships']:,}")
    print(f"  선종별 거리 기준(상위 2.5%) 범위  내 {min(cuts):.2f}~{max(cuts):.2f}  팀 {TEAM_04['cut'][0]}~{TEAM_04['cut'][1]}")
    ok_o = usable == TEAM_04["usable"] and close(rows, TEAM_04["rows"], 0.02) and close(ships, TEAM_04["ships"], 0.03) and abs(min(cuts) - TEAM_04["cut"][0]) < 0.1 and abs(max(cuts) - TEAM_04["cut"][1]) < 0.1
    some = allrows["imo"].drop_duplicates().sample(25, random_state=2)
    alone = pd.concat([op.transform(allrows[allrows["imo"] == i]) for i in some])
    same2 = alone.equals(op.transform(allrows).loc[alone.index])
    print("  이상 운항", "✅" if ok_o else "❌", "/ 한 척 입력 = 전체 결과", "✅" if same2 else "❌")
    ok &= ok_o and same2
    print("\n결과:", "✅ 팀 노트북 결과와 일치" if ok else "❌ 차이가 있음 — 위 항목 확인")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
