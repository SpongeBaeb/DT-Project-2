"""비용 계산 이식 검증: 팀 표 1·2(비용_추정/표1_배별_비용.csv, 표2_변화_분해.csv)를 정답지로, cost/model.py 가 같은 값을 내는지 대조.

    uv run python experiments/A-2_cost/verify_cost.py --team-dir <.../비용_추정> --config config/mrv_pipeline.yaml

예측 모델과 무관하게 '계산식 이식'만 확인하려고, 팀 표에 이미 들어 있는 예측 비율(연료량_t_{대표,하한,상한} ÷ 2025 연료량)을
그대로 입력으로 쓴다. 남는 차이는 입력 데이터(2025년 연료량·ETS 배출량·연료 그룹)가 새 스냅샷에서 달라진 배에서만 생겨야 한다.
팀 표는 소수 셋째 자리까지 반올림돼 있어 허용 오차를 0.0015(백만 원)로 둔다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from cost import model  # noqa: E402
from pipeline.run import load_snapshot  # noqa: E402
from shared.config import load_config  # noqa: E402

TOL = 0.003      # 반올림 오차 (총비용은 세 반올림값의 합 → 최대 약 0.002)
REAL = 0.01      # 이보다 크게 다르면 '실제 차이' (새 스냅샷에서 2025년 입력이 바뀐 배)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--team-dir", required=True)
    ap.add_argument("--config", default="config/mrv_pipeline.yaml")
    a = ap.parse_args()
    team = Path(a.team_dir)
    t1 = pd.read_csv(team / "표1_배별_비용.csv", encoding="utf-8-sig", dtype={"imo": int})
    t2 = pd.read_csv(team / "표2_변화_분해.csv", encoding="utf-8-sig", dtype={"imo": int})
    s, meta, raw = model.load_settings()
    prices = model.load_prices(raw["prices_file"])

    snap = load_snapshot(load_config(a.config))
    sn = snap[snap["year"] == s["base_year"]]
    ships = t1[["imo", "선박명", "선종"]].drop_duplicates("imo")
    d = ships.merge(sn[["imo", "fuel_t", "co2_per_fuel", "ets_co2_t", "ets_co2eq_t", "fuel_group"]], on="imo", how="inner").reset_index(drop=True)
    print(f"팀 표 {len(ships):,}척 중 새 스냅샷 2025년에 있는 배 {len(d):,}척")

    ratios = {}
    base = t1[t1["시나리오"] == "기준"]
    for year in s["years"]:
        by = base[base["연도"] == year].set_index("imo")
        for k in model.KINDS:
            ratios[(year, k)] = (by[f"연료량_t_{k}"].reindex(d["imo"]).to_numpy() / d["fuel_t"].to_numpy())
    m1, m2 = model.build(d, ratios, prices, s)

    def compare(mine: pd.DataFrame, ref: pd.DataFrame, cols: list[str], title: str) -> pd.DataFrame:
        j = mine.merge(ref, on=["imo", "연도", "시나리오"], suffixes=("", "_t"), validate="one_to_one")
        print(f"\n[{title}] 맞춤 {len(j):,}행")
        bad = pd.Series(False, index=j.index)
        for c in cols:
            diff = (j[c] - j[c + "_t"]).abs()
            same = diff.le(TOL) | (j[c].isna() & j[c + "_t"].isna())
            bad |= ~same
            print(f"  {c:18s} 일치 {same.mean() * 100:7.3f}%  최대 차이 {np.nanmax(diff):.3g}")
        real = pd.Series(False, index=j.index)
        for c in cols:
            real |= (j[c] - j[c + "_t"]).abs().gt(REAL)
        print(f"  → 반올림 오차 안에서 모든 열이 일치하는 행 {(~bad).mean() * 100:.2f}%, 실제 차이(>{REAL})가 있는 행 {real.mean() * 100:.3f}%")
        return j.assign(_bad=bad, _real=real)

    j1 = compare(m1, t1, ["연료비_2025", "탄소비용_2025", "총비용_2025", "연료비_대표", "탄소비용_대표", "총비용_대표", "총비용_하한", "총비용_상한", "연료비_가정B_대표", "총비용_가정B_대표"], "표 1")
    j2 = compare(m2, t2, ["총변화_대표", "효율몫_대표", "규제몫", "가격몫", "가격몫_연료", "가격몫_배출권", "효율_크기비중_pct"], "표 2")
    bad_ships = set(j1.loc[j1["_bad"], "imo"]) | set(j2.loc[j2["_bad"], "imo"])
    real_ships = set(j1.loc[j1["_real"], "imo"]) | set(j2.loc[j2["_real"], "imo"])
    print(f"\n반올림 오차를 넘는 차이가 있는 배 {len(bad_ships):,}척, 그중 실제 차이(>{REAL})가 있는 배 {len(real_ships):,}척 / {len(d):,}척")
    if real_ships:
        chk = sn[sn["imo"].isin(real_ships)][["imo", "fuel_t", "ets_co2_t", "ets_co2eq_t", "fuel_group", "source_version"]].head(8)
        print("실제 차이가 있는 배 예시 (새 스냅샷의 2025년 입력):")
        print(chk.to_string(index=False))
    ok = len(real_ships) / len(d) < 0.01
    print("결과:", "✅ 이식 일치 (실제 차이는 입력 데이터가 바뀐 소수의 배)" if ok else "❌ 차이가 큼 — 계산식 점검 필요")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
