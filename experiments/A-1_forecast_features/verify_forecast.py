"""예측 재현 검증: features.py + quantile.py 로 만든 2026~2028 예측이 팀의 forecast_v4.csv 와 같은지 대조.

    uv run python experiments/A-1_forecast_features/verify_forecast.py \
        --merged <...>/mrv_merged_2026-10-06_3183d290.parquet --v1 <...>/03_regression/v1 \
        --team-forecast <...>/회귀_v4_공유/.../v4/forecast_v4.csv

팀 04_final_v4.ipynb 셀 [2] 와 같은 절차 (보정 연도 2025):
  (1) 목표 연도 ≤ 2024 쌍으로 학습 → 2025 쌍 오차로 z 표   (2) 목표 연도 ≤ 2025 전체로 다시 학습 → 2025년 값에서 예측 → z 표로 중심 보정
수준은 팀 원본과 같은 정박 포함 거리당 CO₂, 선종 표기는 팀 원본(영문 원본 이름)으로 맞춘다 (범주 순서까지 같게).

판정 기준 = '잡음 바닥'. LightGBM 은 학습표의 마지막 자리 반올림(1e-15)에도 예측이 평균 3e-3 쯤 달라진다 (행 뽑기·동률 처리).
컴퓨터·numpy 가 다르면 같은 코드도 이만큼 달라지므로, 내 예측이 팀 예측과 다른 정도가 내 학습표에 1e-15 잡음만 넣었을 때의
변화(잡음 바닥)와 같은 크기면 '재현'으로 본다 (평균 차이 ≤ 잡음 바닥의 2배, 상관 ≥ 0.995).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from models.forecast import cii as cii_rules  # noqa: E402
from models.forecast import quantile as Q  # noqa: E402
from models.forecast.features import CAT, COVID, NUM, build_features, delta_clip_bounds, make_pairs  # noqa: E402
from pipeline import mrv_source  # noqa: E402
from pipeline.run import Report  # noqa: E402
from shared.config import load_yaml  # noqa: E402
from shared.preprocess import derive, ensure_schema_columns  # noqa: E402

TYPES13 = ["container", "tanker", "chemical_tanker", "bulk", "general_cargo", "vehicle_carrier", "ro_pax", "gas_carrier",
           "lng_carrier", "ro_ro", "reefer", "cruise", "container_ro_ro"]
BASE, HS = 2025, (1, 2, 3)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--merged", required=True)
    ap.add_argument("--v1", required=True)
    ap.add_argument("--team-forecast", required=True)
    a = ap.parse_args()

    raw = mrv_source.read_merged(Path(a.merged))
    d = mrv_source.to_ship_year_input(raw, load_yaml("config/column_map.yaml"), TYPES13, Report(), min_gt=5000)
    d = derive(ensure_schema_columns(d))
    d = d.assign(co2_per_nm=d["co2_per_nm_kg"])
    clip = delta_clip_bounds(make_pairs(build_features(d, (-np.inf, np.inf), "co2_per_nm_kg"), 1), 2021)
    f = build_features(d, clip, "co2_per_nm_kg")

    # 팀 원본과 같은 범주 순서(영문 원본 선종명, 알파벳순)
    ref_all = pd.read_csv(Path(a.v1) / "features_all_v1.csv", dtype={"imo": str}, encoding="utf-8-sig", usecols=["imo", "year", "ship_type"])
    f["imo"] = f["imo"].astype(str)
    f["ship_type"] = f[["imo", "year"]].merge(ref_all, on=["imo", "year"], how="left")["ship_type"].to_numpy()
    types = sorted(f["ship_type"].unique())
    f["ship_type"] = pd.Categorical(f["ship_type"], categories=types)
    feats = NUM + CAT
    team = pd.read_csv(a.team_forecast, dtype={"imo": str}, encoding="utf-8-sig")
    x25 = f[f["year"] == BASE].reset_index(drop=True)
    d25 = d[d["year"] == BASE].sort_values("imo").reset_index(drop=True)          # CII 열 (cii_ship_type, cii_ratio_2026basis, dwt, gt)
    assert (d25["imo"].astype(str).to_numpy() == x25["imo"].to_numpy()).all()
    has_cii = "thr_de_2026" in team.columns
    print(f"2025년분 {len(x25):,}척 / 팀 예측 {len(team):,}척 / 피처 {len(feats)}개")

    allok = True
    for h in HS:
        y = BASE + h
        p = make_pairs(f, h)
        p["ship_type"] = pd.Categorical(p["ship_type"].astype(str), categories=types)
        (Qc,) = Q.qfit(p[p["target_year"] <= BASE - 1], [p[p["target_year"] == BASE]], feats)
        zq_raw = Q.ztable(Qc, p.loc[p["target_year"] == BASE, "delta"])
        xh = x25.assign(covid_next=int(y in COVID))
        (Qf,) = Q.qfit(p[p["target_year"] <= BASE], [xh], feats)
        m, s, zq = Q.center(Qf, zq_raw)
        mine = pd.DataFrame({"imo": xh["imo"], f"med_{y}": m, f"s_{y}": s, f"q10_{y}": Q.quantile_at(zq, m, s, 0.10), f"q90_{y}": Q.quantile_at(zq, m, s, 0.90)})
        # 잡음 바닥: 내 학습표에 1e-15 상대 잡음만 넣고 같은 절차를 다시 → 그 정도 차이는 '같은 코드'에서도 생긴다
        rng = np.random.default_rng(0)
        pn = p.copy()
        for c in [*NUM, "delta"]:
            v = pn[c].astype(float).to_numpy()
            pn[c] = v * (1 + 1e-15 * rng.standard_normal(len(v)))
        (Qcn,) = Q.qfit(pn[pn["target_year"] <= BASE - 1], [pn[pn["target_year"] == BASE]], feats)
        zqn = Q.ztable(Qcn, pn.loc[pn["target_year"] == BASE, "delta"])
        (Qfn,) = Q.qfit(pn[pn["target_year"] <= BASE], [xh], feats)
        mn, sn, zqn = Q.center(Qfn, zqn)
        noisy = {"med": mn, "s": sn, "q10": Q.quantile_at(zqn, mn, sn, 0.10), "q90": Q.quantile_at(zqn, mn, sn, 0.90)}
        j = mine.merge(team[["imo", f"med_{y}", f"s_{y}", f"q10_{y}", f"q90_{y}"]], on="imo", suffixes=("", "_team"))
        print(f"\n[{y}년, h={h}] 학습 쌍 {int((p['target_year'] <= BASE).sum()):,} / 맞춤 {len(j):,}")
        for c in ("med", "s", "q10", "q90"):
            col = f"{c}_{y}"
            diff = (j[col] - j[col + "_team"]).abs()
            floor = float(np.abs(mine[col].to_numpy() - noisy[c]).mean())
            corr = float(np.corrcoef(j[col], j[col + "_team"])[0, 1])
            ok = diff.mean() <= max(2 * floor, 1e-9) and corr >= 0.995
            allok &= bool(ok)
            print(f"  {col:10s} 팀과 평균 차이 {diff.mean():.2e} (최대 {diff.max():.2e}, 상관 {corr:.5f}) | 잡음 바닥 평균 {floor:.2e}  {'✅' if ok else '❌'}")
        if has_cii:
            tt = team.set_index("imo")
            thr = cii_rules.threshold(d25, np.full(len(d25), y))              # 결정적 계산 → 팀 값과 정확히 같아야 한다
            thr_team = tt.loc[xh["imo"], f"thr_de_{y}"].to_numpy(float)
            both = ~(np.isnan(thr) & np.isnan(thr_team))
            thr_diff = float(np.nanmax(np.abs(thr - thr_team))) if both.any() else 0.0
            nan_same = bool((np.isnan(thr) == np.isnan(thr_team)).all())
            ok_thr = thr_diff < 1e-12 and nan_same
            p_ours, p_noisy, p_team = 1 - Q.cdf(zq, m, s, thr), 1 - Q.cdf(zqn, mn, sn, thr), tt.loc[xh["imo"], f"p_de_{y}"].to_numpy(float)
            dp = float(np.nanmean(np.abs(p_ours - p_team)))
            floor_p = float(np.nanmean(np.abs(p_ours - p_noisy)))
            ok_p = dp <= max(2 * floor_p, 1e-9)
            allok &= bool(ok_thr and ok_p)
            print(f"  D·E 임계값  최대 차이 {thr_diff:.1e}, 빈칸 위치 같음 {nan_same}  {'✅' if ok_thr else '❌'}")
            print(f"  D·E 확률    팀과 평균 차이 {dp:.2e} | 잡음 바닥 평균 {floor_p:.2e}  평균 확률 내 {np.nanmean(p_ours):.3f} / 팀 {np.nanmean(p_team):.3f}  {'✅' if ok_p else '❌'}")
            if h == 1 and "thr_miss_2026" in team.columns:
                tm = cii_rules.miss_threshold(x25["year"].to_numpy())
                tm_team = tt.loc[xh["imo"], "thr_miss_2026"].to_numpy(float)
                ok_tm = float(np.nanmax(np.abs(tm - tm_team))) < 1e-12
                pm, pm_n, pm_t = 1 - Q.cdf(zq, m, s, tm), 1 - Q.cdf(zqn, mn, sn, tm), tt.loc[xh["imo"], "p_miss_2026"].to_numpy(float)
                dpm, fpm = float(np.nanmean(np.abs(pm - pm_t))), float(np.nanmean(np.abs(pm - pm_n)))
                ok_pm = dpm <= max(2 * fpm, 1e-9)
                allok &= bool(ok_tm and ok_pm)
                print(f"  미달 임계값 최대 차이 {float(np.nanmax(np.abs(tm - tm_team))):.1e}  {'✅' if ok_tm else '❌'}")
                print(f"  미달 확률   팀과 평균 차이 {dpm:.2e} | 잡음 바닥 평균 {fpm:.2e}  평균 확률 내 {np.nanmean(pm):.3f} / 팀 {np.nanmean(pm_t):.3f}  {'✅' if ok_pm else '❌'}")
                list_in = (p_ours, pm, p_team, pm_t)
    if has_cii and "thr_miss_2026" in team.columns:
        # 다음 해 리스트: 영업 타깃(D·E 확률 ≥ 0.8) / 관찰(타깃 아님, 지금 A~C, 미달 확률 ≥ p* = 상위 25% 경계). 팀 회귀 문서의 척수와 비교
        rating = d25["cii_rating"].to_numpy()

        def lists(pde, pmiss):
            pstar = float(np.nanquantile(pmiss, 0.75))
            tgt = pde >= 0.8
            wat = ~tgt & np.isin(rating, list("ABC")) & (pmiss >= pstar)
            return int(tgt.sum()), int(wat.sum()), pstar
        mine_l, team_l = lists(list_in[0], list_in[1]), lists(list_in[2], list_in[3])
        print(f"\n[다음 해 리스트] 영업 타깃 / 관찰 / p*   내 확률: {mine_l[0]:,} / {mine_l[1]:,} / {mine_l[2]:.3f}   팀 코드 확률: {team_l[0]:,} / {team_l[1]:,} / {team_l[2]:.3f}   팀 회귀 문서(forecast_v4): 1,171 / 3,150 / 0.715")
        ok_list = abs(mine_l[0] - team_l[0]) <= 0.06 * team_l[0] and abs(mine_l[1] - team_l[1]) <= 0.06 * team_l[1]
        allok &= bool(ok_list)
        print("  내 리스트 척수가 팀 코드 확률로 만든 척수와 6% 이내", "✅" if ok_list else "❌")
    print("\n결과:", "✅ 재현 (팀과의 차이가 잡음 바닥 이내)" if allok else "❌ 잡음 바닥을 넘는 차이가 있음")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
