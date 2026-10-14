"""Sea Marksman 웹(web_sm5)용 데이터: 팀 산출물(artifacts/LATEST) → 화면용 압축 JSON.

팀 정적 JSON(web/public/data, 배마다 파일 1개·약 320MB)과 같은 결과 표에서 만들되, 화면이 한 번에 읽을 수 있게 줄이고
결과 표 약속(형식 2.6)의 선택 열(전체 효율 예측·CII D·E 확률·다음 해 리스트·유지 확률·유형 소속 확률)과
비용 표 1~3을 함께 싣는다. 계산은 새로 하지 않는다 (값은 결과 표·비용 표 그대로, 반올림만).

  python -m publish.web_sm --out web_sm5/public/data          (먼저 tasks.py build · cost · list · evaluate)

출력
  ships.json  배마다 마지막 보고 연도 한 행 (진단·찾기·선대·리스트)
  hist.json   배별 연도 이력 [연도, 해상 효율, 동급 중간, 정박 CO₂, 정박 같은 조건, 해상 시간, 전체 거리당 CO₂, 거리, 같은 조건 예측, 위치 z, CII 등급,
              CII 비율(2026 기준), CO₂ 합계]
  cost.json   기준 연도 보고 배의 2026~2028 비용 (백만 원, 표 1~3)
  meta.json   모델·데이터 판, 선종별 모델 요약, 검증, 리스트 기준, 비용 설정·가격, 이름표
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from contracts.tables import CAUSE_FACTORS, SIGNAL_COLS
from models.bundle import ModelBundle
from pipeline.run import load_snapshot
from publish.artifacts import latest_dir
from shared.config import ROOT, load_config, load_yaml, path

# 결과 표 원인 막대 → 화면 키
FACTOR_KEY = {"size": "size", "speed_pattern": "speed", "sea_time": "hours", "eu_exposure": "intra", "age_design": "age",
              "fuel": "fuel", "ice": "ice", "other": "other", "unexplained": "rest"}
SIG_KEY = {"sig_berth": "berth", "sig_short": "short", "sig_fuel": "fuel", "sig_report": "report", "sig_special": "special"}


def r(x, d=1):
    if x is None or x is pd.NA:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if not math.isfinite(x) else round(x, d) if d else int(round(x))


def s_(x):
    return x if isinstance(x, str) and x.strip() else None


def ships_and_hist(res: pd.DataFrame, snap: pd.DataFrame, lst: pd.DataFrame | None):
    snap = snap.set_index(["imo", "year"])
    res = res.sort_values(["imo", "year"])
    names = snap.reset_index().sort_values("year").groupby("imo")["name"].apply(lambda s: list(dict.fromkeys(s.dropna().astype(str))))
    rank = {} if lst is None else {int(i): (c, int(k)) for i, c, k in zip(lst["IMO"], lst["list_code"], lst["순위"])}
    last = res.groupby("imo").tail(1)
    ships = []
    for row in last.itertuples(index=False):
        x = snap.loc[(row.imo, row.year)]
        rd = row._asdict()
        name = s_(x["name"]) or f"IMO {row.imo}"
        sig = [SIG_KEY[c] for c in SIGNAL_COLS if bool(rd[c])]
        fc = [[r(rd[f"fc_h{h}_p{q}"]) for q in (50, 10, 90)] for h in (1, 2, 3)]
        fct = [[r(rd[f"fct_h{h}_p{q}"]) for q in (50, 10, 90)] for h in (1, 2, 3)]
        pde = [r(rd[f"p_de_h{h}"], 3) for h in (1, 2, 3)]
        lc = rank.get(int(row.imo))
        rec = {
            "imo": int(row.imo), "ly": int(row.year), "n": name, "on": [n for n in names.get(row.imo, []) if n != name][-4:] or None,
            "t": row.ship_type, "dwt": r(x["dwt"], 0), "gt": r(x["gt"], 0), "loa": r(x["length_m"], 1), "b": r(x["build_year"], 0), "age": int(x["age"]),
            "co": s_(x["company"]), "ice": s_(x["ice_class"]), "ek": s_(x["eedi_kind"]), "ev": r(x["eedi"], 2), "fg": s_(x["fuel_group"]),
            "cpf": r(x["co2_per_fuel"], 3), "co2": r(x["co2_t"], 0), "dist": r(x["distance_nm"], 0), "hrs": r(x["sea_hours"], 0),
            "spd": r(x["avg_speed_kn"], 2), "intra": r(x["eu_share"], 3),
            "ets": r(x["ets_co2_t"] / x["co2_t"], 3) if pd.notna(x["ets_co2_t"]) and x["co2_t"] > 0 else None,
            "co2pn": r(x["co2_per_nm_kg"], 1), "cii": s_(x["cii_rating"]), "cii26": s_(x["cii_rating_2026basis"]), "ciir": r(x["cii_ratio_2026basis"], 3),
            "sea": r(row.sea_eff_actual), "peer": r(row.sea_eff_peer_median), "exp": r(row.sea_eff_expected), "sq": int(row.size_bin) - 1,
            "c": {FACTOR_KEY[f]: r(rd[f"contrib_{f}"] * 100, 2) for f in CAUSE_FACTORS},
            "z": r(row.position_z, 2), "zy": int(row.position_n_years),
            "bt": r(row.berth_actual_t, 0), "be": r(row.berth_expected_t, 0), "br": r(row.berth_ratio, 2), "bz": r(row.berth_z, 2),
            "brp": [r(row.berth_ratio_hist_min, 2), r(row.berth_ratio_hist_max, 2)] if pd.notna(row.berth_ratio_hist_min) else None,
            "bhz": r(row.berth_hist_z, 2), "bs": r(row.berth_actual_t / x["co2_t"], 3) if x["co2_t"] > 0 else None,
            "sig": sig or None,
            "fc": fc if all(v is not None for f in fc for v in f) else None,
            "fct": fct if all(v is not None for f in fct for v in f) else None,
            "pde": pde if all(v is not None for v in pde) else None, "pm": r(rd["p_miss_h1"], 3),
            "lst": lc[0] if lc else None, "lr": lc[1] if lc else None,
            "pp": r(rd["persist_prob"], 3), "pup": s_(rd["persist_up"]), "pdn": s_(rd["persist_down"]),
            "tx": r(rd["type_exposure"], 0), "txp": r(rd["type_exposure_prob"], 2), "ta": r(rd["type_age_design"], 0), "tap": r(rd["type_age_design_prob"], 2),
            "oo": bool(row.ops_outlier) or None,
            "w": [w for w in str(row.warnings).split(" | ") if w] or None,
        }
        ships.append({k: v for k, v in rec.items() if v is not None})

    hist = {}
    for imo, g in res.groupby("imo"):
        rows = []
        for row in g.itertuples(index=False):
            x = snap.loc[(row.imo, row.year)]
            rows.append([int(row.year), r(row.sea_eff_actual), r(row.sea_eff_peer_median), r(row.berth_actual_t, 0), r(row.berth_expected_t, 0),
                         r(x["sea_hours"], 0), r(x["co2_per_nm_kg"]), r(x["distance_nm"], 0), r(row.sea_eff_expected), r(row.position_z, 2),
                         s_(x["cii_rating"]), r(x["cii_ratio_2026basis"], 3), r(x["co2_t"], 0)])
        hist[str(int(imo))] = rows
    return ships, hist


def cost_tables(cdir: Path) -> dict:
    """비용 표 1~3 → {imo: {"b": [연료비, 탄소비용, 총비용] (2025), "fg": 연료그룹, "k": 표시,
                          "s": {시나리오: [[총비용 대표·하한·상한, 연료비, 탄소비용, 동급 대비 차이, 총변화, 효율몫, 규제몫, 가격몫_연료, 가격몫_배출권, 총비용_가정B] × 연도]}}}"""
    t1, t2, t3 = (pd.read_parquet(cdir / f) for f in ("표1_배별_비용.parquet", "표2_변화_분해.parquet", "표3_동급_대비.parquet"))
    key = ["imo", "연도", "시나리오"]
    m = t1.merge(t2.drop(columns=["선박명", "선종"]), on=key).merge(t3[key + ["동급대비_차이", "동급대비_2025_pct"]], on=key)
    out: dict[str, dict] = {}
    for imo, g in m.sort_values(["imo", "연도"]).groupby("imo"):
        g0 = g.iloc[0]
        e = {"b": [r(g0["연료비_2025"]), r(g0["탄소비용_2025"]), r(g0["총비용_2025"])], "fg": s_(g0["연료그룹"]), "k": s_(g0["표시"]),
             "pg": r(g0["동급대비_2025_pct"]), "s": {}}
        if g["총비용_대표"].isna().all():      # LPG 추정 등: 연료비 미산출 → 사유만 싣는다
            del e["s"]
            out[str(int(imo))] = e
            continue
        for sc, h in g.groupby("시나리오"):
            e["s"][sc] = [[r(v) for v in (y["총비용_대표"], y["총비용_하한"], y["총비용_상한"], y["연료비_대표"], y["탄소비용_대표"], y["동급대비_차이"],
                                          y["총변화_대표"], y["효율몫_대표"], y["규제몫"], y["가격몫_연료"], y["가격몫_배출권"], y["총비용_가정B_대표"])]
                          for _, y in h.iterrows()]
        out[str(int(imo))] = e
    return out


def illusion_stats(res: pd.DataFrame, snap: pd.DataFrame, base_year: int) -> dict:
    """CII 한 글자가 만드는 네 가지 착시의 근거 수치 (발표 A 파트 4장). 모두 기준 연도 보고 선박, CII 등급(근사)이 있는 배.
    ① 정박: 나쁜 쪽 끝 2.5%의 정박 신호 비율 vs 가운데 50%
    ② 조건: 같은 선종 안 평균 속력 4분위별 D·E 비율 (가장 느린 4분위 vs 나머지)
    ③ 한 해: 전년보다 해상 효율이 20% 이상 나빠진 배 중 이듬해 오른 폭의 절반 이상을 되돌린 비율 (모든 연도 쌍)
    ④ 보고 오류: 양 끝 5%의 착시 신호 비율 vs 가운데, 좋은 쪽 끝 2.5%의 신호 비율"""
    k = ["imo", "year"]
    d = res[res.year == base_year].merge(snap[k + ["cii_ratio_2026basis", "cii_rating", "avg_speed_kn"]], on=k)
    d = d[d["cii_ratio_2026basis"].notna()].copy()
    q = d["cii_ratio_2026basis"].rank(pct=True)
    worst, best, mid = q > 0.975, q <= 0.025, (q > 0.25) & (q <= 0.75)
    ends5 = (q > 0.95) | (q <= 0.05)
    sp = d.groupby("ship_type")["avg_speed_kn"].rank(pct=True)
    slow, de = sp <= 0.25, d["cii_rating"].isin(["D", "E"])
    pct = lambda m, v: round(float(v[m].mean()) * 100, 1) if m.any() else None
    # ③ 해상 효율 연간 변화
    h = res[k + ["sea_eff_actual"]].sort_values(k)
    h["prev"] = h.groupby("imo")["sea_eff_actual"].shift()
    h["next"] = h.groupby("imo")["sea_eff_actual"].shift(-1)
    h["prev_y"] = h.groupby("imo")["year"].shift()
    h["next_y"] = h.groupby("imo")["year"].shift(-1)
    j = h[(h.prev_y == h.year - 1) & (h.next_y == h.year + 1) & (h.sea_eff_actual >= h.prev * 1.2)]
    back = (j.sea_eff_actual - j.next) >= 0.5 * (j.sea_eff_actual - j.prev)
    return {
        "n": int(len(d)),
        "berth": {"worst": pct(worst, d.sig_berth), "mid": pct(mid, d.sig_berth), "n_worst": int(worst.sum())},
        "speed": {"slow_de": pct(slow, de), "other_de": pct(~slow, de)},
        "year": {"n_jump": int(len(j)), "reverted": round(float(back.mean()) * 100, 1) if len(j) else None},
        "report": {"ends5": pct(ends5, d.sig_any), "mid": pct(mid, d.sig_any), "best": pct(best, d.sig_any),
                   "best_fuel": pct(best, d.sig_fuel)},
    }


def meta_of(adir: Path, bundle: ModelBundle, ships: list[dict], cfg: dict, base_year: int, sources: list[str], illusions: dict) -> dict:
    stg = {type(s).__name__: s for s in bundle.stages}
    cr, lr, tt = stg.get("CommonResidualBaseline"), stg.get("ListRule"), stg.get("TeamTypes")
    S = pd.DataFrame(ships)
    cur = S[S.ly == base_year]
    clean = cur[cur["sig"].isna()]
    acc = json.loads((adir / "acceptance.json").read_text(encoding="utf-8")) if (adir / "acceptance.json").exists() else None
    if acc:   # 합격 기준 판정표 (python tasks.py evaluate) → 화면용
        sel_until = load_yaml("config/acceptance.yaml")["position"]["select_until"]
        acc = {"position": {**acc["metrics"]["position"], "select_until": sel_until}, "verdict": acc["verdict"], "metrics": acc["metrics"]}
    man = json.loads((adir / "manifest.json").read_text(encoding="utf-8"))
    cost_set = json.loads((adir / "cost" / "settings.json").read_text(encoding="utf-8")) if (adir / "cost" / "settings.json").exists() else {}
    cost_yaml = load_yaml("config/cost.yaml") if path("config/cost.yaml").exists() else {"settings": {}}
    prices = pd.read_csv(path("config/cost_prices.csv"))
    from models.cluster.team import EXPOSURE_NAMES, PROFILE_NAMES
    from models.forecast.persist import REASON_GROUPS
    return {
        "generated": pd.Timestamp.today().strftime("%Y-%m-%d"), "base_year": base_year,
        "n_ships": int(len(cur)), "n_all": int(len(S)),
        "model_version": bundle.meta["model_version"], "data_hash": bundle.meta["data_hash"], "result_table_version": bundle.meta["result_table_version"],
        "sources": sources,
        "stages": [s["use"].split(":")[1] for s in bundle.meta["stages"]],
        "thresholds": cfg["thresholds"], "main_engine_share": cfg.get("physics", {}).get("main_engine_share", {}),
        "types": {t: {k: v for k, v in i.items() if k in ("n", "ships", "r2", "speed_elasticity", "speed_is_wait")} for t, i in (cr.type_info if cr else {}).items()},
        "factors": {FACTOR_KEY[f]: l for f, l in CAUSE_FACTORS.items()},
        "funnel": {"all": int(len(cur)), "clean": int(len(clean)), "high": int((clean["z"].fillna(-99) >= cfg["thresholds"]["z_consistently_high"]).sum()),
                   "high_all": int((cur["z"].fillna(-99) >= cfg["thresholds"]["z_consistently_high"]).sum())},
        "validation": acc,
        "list": {"year": base_year + 1, "p_star": round(float(lr.p_star), 3) if lr is not None and lr.p_star is not None else None,
                 "de_cut": lr.de_cut if lr else None, "watch_ratings": lr.params.get("watch_ratings") if lr else None,
                 "target": int((cur["lst"] == "target").sum()) if "lst" in cur else 0, "watch": int((cur["lst"] == "watch").sum()) if "lst" in cur else 0},
        "type_names": {"exposure": EXPOSURE_NAMES, "profile": PROFILE_NAMES, "n_fleet": getattr(tt, "n_fleet", None)},
        "illusions": illusions,
        "persist": {"groups": list(REASON_GROUPS), "base_rate": round(float(stg["PersistProbability"].base_rate), 3) if "PersistProbability" in stg else None},
        "cost": {"unit": "백만 원", "years": cost_set.get("years", {}).get("value"),
                 "ets_share": cost_set.get("ets_share", {}).get("value"),
                 "settings": [[k, v.get("status"), (cost_yaml["settings"].get(k) or {}).get("note", "")] for k, v in cost_set.items() if v.get("status") != "확정"],
                 "prices": prices.to_dict(orient="records")},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="web_sm5/public/data")
    ap.add_argument("--config", default=None)
    a = ap.parse_args()
    cfg = load_config(a.config)
    adir = latest_dir()
    out = path(a.out)
    bundle = ModelBundle.load(adir)
    res = pd.read_parquet(adir / "result_table.parquet")
    snap = load_snapshot(cfg)
    base_year = int(res["year"].max())
    lfile = adir / "list" / f"리스트_{base_year + 1}.parquet"
    lst = pd.read_parquet(lfile) if lfile.exists() else None

    ships, hist = ships_and_hist(res, snap, lst)
    cost = cost_tables(adir / "cost") if (adir / "cost").exists() else {}
    meta = meta_of(adir, bundle, ships, cfg, base_year, sorted(snap["source_version"].dropna().astype(str).unique().tolist()),
                   illusion_stats(res, snap, base_year))

    tmp = out.with_name(out.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    for name, obj in (("ships.json", ships), ("hist.json", hist), ("cost.json", cost), ("meta.json", meta)):
        (tmp / name).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=lambda o: o.item() if hasattr(o, "item") else str(o)), encoding="utf-8")
    if out.exists():
        shutil.rmtree(out)
    tmp.rename(out)
    sizes = {p.name: f"{p.stat().st_size / 1e6:.1f}MB" for p in out.iterdir()}
    print(f"[web_sm] {out.relative_to(ROOT)}  선박 {len(ships):,}척 (기준 연도 {meta['n_ships']:,})  {sizes}")
    print(f"  선별: {meta['funnel']}  리스트: {meta['list']}")


if __name__ == "__main__":
    main()
