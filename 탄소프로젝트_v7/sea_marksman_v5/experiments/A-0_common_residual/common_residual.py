"""공통 잔차 모델 (담당: 배성우). 팀의 모든 분석이 같이 쓰는 "같은 조건이면 보통 이만큼 쓴다" 기준과 원인 분해.

실행 (web_v2_package 폴더에서):  python 공통잔차/common_residual.py
입력:  MRV 파이프라인 mrv_merged.parquet (데이터생성코드/data_source.py)
출력:  공통잔차/결과/common_residual.parquet   배·연도별 잔차, 판정값, 요인별 기여와 오차
       공통잔차/결과/coefficients.csv           선종별 계수, 배 단위 군집 오차, 부호 점검
       공통잔차/결과/summary.json               출처(원본 버전·해시), 선종별 설명력·퍼짐, 검증 결과

모델 (선종마다 따로, 2018~2025 전 연도를 함께):
  ln(거리당 CO2) = 연도 효과 + 크기(ln, ln²) + 속력(ln, ln²) + 정박 비중 + 역내 비중 + ln(해상 시간)
                   + 선령 + 설계 효율 지표(종류별 값, 없음 표시) + 내빙 + 대체연료 (+ 로팩스 고속선)
  - 적재는 넣지 않음 (계수 ≈ 0, 넣어도 설명력 같음)
  - 속력 탄력성(선종 중앙 속력에서)이 ELAST_WAIT 이하인 선종은 속력 기여를 "대기 추정"으로 표시
잔차 = 실제 − 예측.  판정용 값 = 여러 해 잔차를 보고 연수에 따라 선종 평균 쪽으로 줄여 잡은 평균.
원인 분해 (배·연도마다, 같은 선종·같은 해·같은 크기 4분위 = 동급 기준):
  ln(실제) − ln(동급 기준값) = Σ 요인 기여 + 설명되지 않는 부분     (항상 정확히 맞음)
  요인 기여 = 계수 · (이 배 값 − 동급 중간 값),  설명되지 않는 부분 = 잔차 − 동급 잔차 중간값
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "데이터생성코드"))
from data_source import load, source  # noqa: E402

OUT = HERE / "결과"
METRIC = "co2_per_nm"      # 팀 결정 전 권장안. 에너지 기준으로 바꾸려면 이 열만 바꾼다
BASE = 2025
ELAST_WAIT = 0.1
MIN_N = 100                # 선종 회귀 최소 행 수
VALIDATE_ASOF = 2023       # 시간 분할 검증: 이 해까지로 고르고 다음 두 해로 평가

# 요인 묶음 = 그래프 막대 하나. (열 목록, 막대 이름, 기대 부호: 해당 변수가 클수록 CO2/nm 가 + 인가)
GROUPS = {
    "size":   (["ln_cap", "ln_cap2"], "크기 (체급 안 차이)", None),
    "speed":  (["ln_v", "ln_v2"], "속력", "+"),
    "berth":  (["berth"], "정박 중 배출", "+"),
    "intra":  (["intra"], "EU 역내 항해", None),
    "hours":  (["ln_h"], "EU 해상 시간", None),
    "age":    (["age"], "선령", "+"),
    "design": (["eff_c", "k_EEDI", "k_EEXI", "k_none"], "설계 효율 지표", "+"),
    "ice":    (["ice"], "내빙 선급", "+"),
    "alt":    (["alt"], "대체연료", "-"),
    "hsc":    (["hsc"], "고속선", "+"),
}
SIGN_VAR = {"berth": "berth", "age": "age", "design": "eff_c", "ice": "ice", "alt": "alt", "hsc": "hsc"}


def prepare(d: pd.DataFrame) -> pd.DataFrame:
    d = d[(d.gross_tonnage >= 5000) & (d[METRIC] > 0) & (d.speed_kn > 0) & (d.time_at_sea_h > 0) & (d.cii_capacity > 0)].copy()
    d["ln_y"] = np.log(d[METRIC])
    d["ln_cap"] = np.log(d.cii_capacity); d["ln_cap2"] = d.ln_cap ** 2
    d["ln_v"] = np.log(d.speed_kn); d["ln_v2"] = d.ln_v ** 2
    d["berth"] = d.berth_share.fillna(d.groupby("ship_type").berth_share.transform("median"))
    d["intra"] = d.intra_eu_share.fillna(d.groupby("ship_type").intra_eu_share.transform("median"))
    d["ln_h"] = np.log(d.time_at_sea_h)
    d["age"] = d.ship_age.astype(float)
    kind = d.tech_eff_kind.where(d.tech_eff_kind.isin(["EEDI", "EEXI", "EIV"]), "none")
    ln_eff = np.log(d.tech_eff_value.where((d.tech_eff_value > 0) & (kind != "none")))
    # 설계 지표 값은 종류·선종마다 수준이 달라, 선종×종류 중앙값과의 차이로 쓴다 (없으면 0 + 없음 표시)
    d["eff_c"] = (ln_eff - ln_eff.groupby([d.ship_type, kind]).transform("median")).fillna(0.0)
    for k in ["EEDI", "EEXI"]:
        d[f"k_{k}"] = (kind == k).astype(float)
    d["k_none"] = ((kind == "none") | ln_eff.isna()).astype(float)
    d["ice"] = d.ice_class.notna().astype(float)
    d["alt"] = d.fuel_alt.astype(str).eq("True").astype(float)
    d["hsc"] = d.cii_hsc_proxy.astype(str).eq("True").astype(float)
    d["size_q"] = d.groupby(["ship_type", "year"]).ln_cap.transform(lambda s: pd.qcut(s, 4, labels=False, duplicates="drop"))
    return d


def fit_type(g: pd.DataFrame):
    cols = [c for grp in GROUPS.values() for c in grp[0] if not (c == "hsc" and g.ship_type.iloc[0] != "Ro-pax ship")]
    cols = [c for c in cols if g[c].std() > 0]                          # 변동 없는 변수(예: 내빙선이 없는 선종)는 뺀다
    years = sorted(g.year.unique())[1:]
    X = np.column_stack([np.ones(len(g)), g[cols].to_numpy(float)] + [(g.year == y).to_numpy(float) for y in years])
    y = g.ln_y.to_numpy()
    XtX_inv = np.linalg.pinv(X.T @ X)
    b = XtX_inv @ X.T @ y
    e = y - X @ b
    # 배 단위 군집 오차 (같은 배의 여러 해는 독립이 아니다)
    S = np.zeros((X.shape[1], X.shape[1]))
    for _, idx in pd.Series(np.arange(len(g))).groupby(g.imo.to_numpy()):
        s = X[idx.to_numpy()].T @ e[idx.to_numpy()]
        S += np.outer(s, s)
    G = g.imo.nunique()
    V = XtX_inv @ S @ XtX_inv * G / max(G - 1, 1)
    names = ["const"] + cols
    coef = pd.Series(b[: len(names)], index=names)
    cov = pd.DataFrame(V[: len(names), : len(names)], index=names, columns=names)
    r2 = 1 - e.var() / y.var()
    return coef, cov, X @ b, r2


def main():
    raw, meta = load()
    d = prepare(raw)
    rows, coefs, types = [], [], {}
    for t, g in d.groupby("ship_type"):
        if len(g) < MIN_N:
            continue
        coef, cov, pred, r2 = fit_type(g)
        g = g.assign(expected=pred, resid=g.ln_y - pred)
        vm = g.ln_v.median()
        elast = coef.get("ln_v", 0) + 2 * coef.get("ln_v2", 0) * vm
        wait = bool(elast <= ELAST_WAIT)
        # 동급 기준: 같은 선종·해·크기 4분위의 각 변수 중간값과 잔차 중간값
        peer = ["year", "size_q"]
        allvars = [c for c in coef.index if c != "const"]
        ref = g.groupby(peer)[allvars].transform("median")
        m_peer = g.groupby(peer).resid.transform("median")
        for gk, (cols, _, _) in GROUPS.items():
            cs = [c for c in cols if c in coef.index]
            if not cs:
                g[f"c_{gk}"] = 0.0; g[f"se_{gk}"] = 0.0; continue
            D = (g[cs] - ref[cs]).to_numpy(float)
            g[f"c_{gk}"] = D @ coef[cs].to_numpy()
            Vg = cov.loc[cs, cs].to_numpy()
            g[f"se_{gk}"] = np.sqrt(np.einsum("ij,jk,ik->i", D, Vg, D).clip(min=0))
        g["c_rest"] = g.resid - m_peer
        ccols = [f"c_{k}" for k in GROUPS] + ["c_rest"]
        g["peer_ln"] = g.ln_y - g[ccols].sum(axis=1)                      # 동급 기준값 (ln)
        g["gap"] = g.ln_y - g.peer_ln
        rows.append(g)
        for v in coef.index:
            grp = next((k for k, (cs, _, _) in GROUPS.items() if v in cs), "const" if v == "const" else "")
            exp_sign = GROUPS[grp][2] if grp in GROUPS and SIGN_VAR.get(grp) == v else None
            b, se = float(coef[v]), float(np.sqrt(cov.loc[v, v]))
            ok = None if exp_sign is None else ((b > 0) == (exp_sign == "+")) or abs(b) < 2 * se
            coefs.append({"ship_type": t, "var": v, "group": grp, "coef": b, "se": se, "t": b / se if se else np.nan,
                          "expected_sign": exp_sign, "sign_ok": ok})
        coefs.append({"ship_type": t, "var": "speed_elasticity", "group": "speed", "coef": float(elast), "se": np.nan, "t": np.nan,
                      "expected_sign": "+", "sign_ok": True if wait or elast > 0 else False,
                      "note": "대기 추정으로 해석" if wait else ""})
        types[t] = {"n": int(len(g)), "ships": int(g.imo.nunique()), "r2": round(float(r2), 3),
                    "resid_sd_pct": round(float((np.exp(g.resid.std()) - 1) * 100), 1),
                    "speed_elasticity": round(float(elast), 3), "speed_is_wait": wait}
    R = pd.concat(rows)
    # 속력이 대기 추정인 선종은 막대 이름이 달라지므로 표시 열을 둔다
    R["speed_label"] = np.where(R.ship_type.map(lambda t: types[t]["speed_is_wait"]), "대기 추정 (평균 속력)", "속력")

    # 판정용: 여러 해 잔차를 줄여 잡은 평균 (선종·해 중간값을 뺀 잔차 기준)
    R["resid_c"] = R.resid - R.groupby(["ship_type", "year"]).resid.transform("median")

    def shrink(upto):
        S = R[R.year <= upto]
        latest = S.sort_values("year").groupby("imo").ship_type.last()          # 선종 표기가 바뀐 배는 마지막 해의 선종으로 한 번만
        S = S.assign(ship_type=S.imo.map(latest))
        out = []
        for t, g in S.groupby("ship_type"):
            mean = g.groupby("imo").resid_c.mean(); n = g.groupby("imo").size()
            sw = ((g.resid_c - g.imo.map(mean)) ** 2).sum() / max(len(g) - len(mean), 1)
            sb = max(mean.var() - sw * (1 / n).mean(), 1e-6)
            k = sb / (sb + sw / n)
            sh = mean * k
            sig = sh.std()
            out.append(pd.DataFrame({"ship_type": t, "resid_shrunk": sh, "shrink_k": k, "n_years": n, "z": (sh - sh.median()) / sig, "sigma": sig}))
        return pd.concat(out)

    J = shrink(BASE)
    last = R[R.year == BASE].set_index("imo").join(J.drop(columns="ship_type"))
    # 시간 분할 검증
    Jv = shrink(VALIDATE_ASOF)
    fut = R[R.year.isin([VALIDATE_ASOF + 1, VALIDATE_ASOF + 2])].groupby("imo").resid_c.mean()
    one = R[R.year == VALIDATE_ASOF].set_index("imo")[["ship_type", "resid_c"]]

    def topcheck(score, typ):
        x = pd.DataFrame({"s": score, "t": typ}).join(fut.rename("f"), how="inner").dropna()
        top = x[x.groupby("t").s.rank(pct=True) >= 0.975]
        return int(len(top)), round(float((top.f > np.log(1.1)).mean()), 3), round(float((np.exp(top.f.median()) - 1) * 100), 1)

    n1, k1, m1 = topcheck(one.resid_c, one.ship_type)
    same = Jv.index.intersection(one.index)                                  # 2023에 보고한 같은 배들끼리 비교
    n2, k2, m2 = topcheck(Jv.resid_shrunk.loc[same], Jv.ship_type.loc[same])
    pv = R.pivot_table(index="imo", columns="year", values="resid")
    validation = {
        "asof": VALIDATE_ASOF, "rule": "선종별 상위 2.5% → 다음 두 해 평균 잔차가 +10% 넘게 유지된 비율",
        "single_year": {"n": n1, "still_over10": k1, "future_median_pct": m1},
        "shrunk": {"n": n2, "still_over10": k2, "future_median_pct": m2},
        "persistence_corr_2024_2025": round(float(pv[[2024, 2025]].corr().iloc[0, 1]), 3),
    }
    # 완료 기준 1: 막대 합 = 격차
    ccols = [f"c_{k}" for k in GROUPS] + ["c_rest"]
    identity_err = float((R[ccols].sum(axis=1) - R.gap).abs().max())

    OUT.mkdir(exist_ok=True)
    keep = ["imo", "year", "ship_type", "name", METRIC, "expected", "resid", "resid_c", "peer_ln", "gap", "size_q", "speed_label",
            "time_at_sea_h"] + ccols + [f"se_{k}" for k in GROUPS]
    R[keep].rename(columns={METRIC: "actual"}).assign(expected=lambda x: np.exp(x.expected), peer=lambda x: np.exp(x.peer_ln)) \
        .to_parquet(OUT / "common_residual.parquet", index=False)
    last[["ship_type", "resid_shrunk", "shrink_k", "n_years", "z", "sigma"]].reset_index().to_parquet(OUT / "judgment_2025.parquet", index=False)
    C = pd.DataFrame(coefs)
    C.to_csv(OUT / "coefficients.csv", index=False, encoding="utf-8-sig")
    bad = C[C.sign_ok == False]  # noqa: E712
    summary = {"data": source(meta), "metric": METRIC, "base_year": BASE, "types": types, "validation": validation,
               "identity_max_error": identity_err,
               "sign_problems": bad[["ship_type", "var", "coef", "se"]].round(3).to_dict("records"),
               "groups": {k: v[1] for k, v in GROUPS.items()}}
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")

    print("데이터:", summary["data"]["versions"], summary["data"]["data_hash"])
    print(f"행 {len(R):,} · 선박 {R.imo.nunique():,} · 선종 {len(types)}")
    print("막대 합 = 격차 최대 오차:", f"{identity_err:.2e}")
    print(pd.DataFrame(types).T[["n", "r2", "resid_sd_pct", "speed_elasticity", "speed_is_wait"]].to_string())
    print("부호 점검에 걸린 계수:", len(bad)); print(bad[["ship_type", "var", "coef", "se"]].round(3).to_string(index=False) if len(bad) else "  없음")
    print("검증:", validation)


if __name__ == "__main__":
    main()
