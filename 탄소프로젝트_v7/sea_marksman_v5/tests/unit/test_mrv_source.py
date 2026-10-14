"""팀 MRV 전처리 파이프라인 결과 → SHIP_YEAR 어댑터 (pipeline/mrv_source.py).

실제 데이터 없이, 합성 표본을 팀 통합 파일의 열 이름으로 바꿔 만든 가짜 통합 파일로 확인한다.
"""
import numpy as np
import pandas as pd
import pytest

from contracts.tables import SHIP_YEAR
from pipeline import mrv_source
from pipeline.run import Report, add_company_history, clean_and_derive, load_snapshot, run
from shared.config import load_yaml

EN = {"container": "Container ship", "tanker": "Oil tanker", "bulk": "Bulk carrier", "ro_pax": "Ro-pax ship"}


@pytest.fixture(scope="module")
def merged(snapshot):
    """팀 통합 파일처럼 보이는 표 (열 이름과 일부 군더더기 열 포함)."""
    s = snapshot.copy()
    m = pd.DataFrame({
        "year": s["year"], "imo": s["imo"].astype(str), "name": s["name"], "ship_type": s["ship_type"].map(EN),
        "ship_type_raw": s["ship_type"].map(EN), "company_name": s["company"], "ice_class": s["ice_class"],
        "fuel_t": s["fuel_t"], "co2_t": s["co2_t"], "co2_berth_t": s["berth_co2_t"], "co2_between_eu_t": s["co2_intra_eu_t"],
        "co2_ets_t": s["ets_co2_t"], "ets_co2_t": s["ets_co2_t"] * 2,            # 추정 포함 열: 보고값(co2_ets_t)이 이겨야 한다
        "time_at_sea_h": s["sea_hours"], "co2_per_nm": s["co2_per_nm_kg"], "distance_nm": s["distance_nm"],
        "dwt": s["dwt"], "gross_tonnage": s["gt"], "length_m": s["length_m"], "built_year": s["build_year"],
        "tech_eff_value": s["eedi"], "tech_eff_kind": np.where(s["eedi"].notna(), "EEDI", None),
        "cii_ship_type": s["ship_type"].map(EN), "cii_capacity": s["dwt"], "cii_hsc_proxy": s["ship_type"].eq("ro_pax"),
        "fuel_group": "석유계", "avg_load": s["cargo_t"], "avg_load_basis": "mass", "avg_load_invalid": False,
        "mrv_file_version": "v60",
    })
    m.loc[m["year"] == 2018, "mrv_file_version"] = "v275"
    return m


def _colmap():
    return load_yaml("config/column_map.yaml")


def test_converts_to_a_valid_ship_year(merged):
    rep = Report()
    d = mrv_source.to_ship_year_input(merged, _colmap(), list(EN), rep)
    d = clean_and_derive(add_company_history(d), rep)
    out = SHIP_YEAR.validate(d, extra="drop")
    assert len(out) == len(merged)
    assert out["imo"].dtype.kind == "i"
    assert set(out["ship_type"]) == set(EN)
    assert (out["source_version"].str.split(":").str[0] == out["year"].astype(str)).all()
    assert out.loc[out["year"] == 2018, "source_version"].str.endswith(":275").all()
    # 추정 포함 열이 아니라 보고값을 쓴다
    first = merged.iloc[0]
    assert out.loc[(out["imo"] == int(first["imo"])) & (out["year"] == first["year"]), "ets_co2_t"].iloc[0] == pytest.approx(first["co2_ets_t"], nan_ok=True)
    assert out["hsc_proxy"].dtype == bool and out["fuel_group"].eq("석유계").all()


def test_filters_unknown_types_and_small_ships(merged):
    m = merged.copy()
    m.loc[m.index[:5], "ship_type"] = "Submarine"
    m.loc[m.index[5:12], "gross_tonnage"] = 100.0
    rep = Report()
    d = mrv_source.to_ship_year_input(m, _colmap(), list(EN), rep, min_gt=5000)
    steps = {s["step"]: s for s in rep.steps}
    assert steps["harmonize"]["dropped_unknown_type"] == {"Submarine": 5}
    assert steps["gt_filter"]["dropped"] >= 7
    assert "Submarine" not in set(d["ship_type"])


def test_missing_required_columns_are_reported(merged):
    with pytest.raises(KeyError, match="필요한 열"):
        mrv_source.to_ship_year_input(merged.drop(columns=["co2_berth_t"]), _colmap(), list(EN), Report())


def test_cargo_only_when_confirmed_as_mass(merged):
    m = merged.copy()
    m["avg_load_basis"] = "volume"
    d = mrv_source.to_ship_year_input(m, _colmap(), list(EN), Report())
    assert d["cargo_t"].isna().all()


def test_full_run_from_merged_file(cfg, merged, tmp_path, monkeypatch):
    p = tmp_path / "mrv_merged.parquet"
    merged.to_parquet(p, index=False)
    c = {**cfg, "data": {**cfg["data"], "source": "mrv_pipeline", "ship_types": list(EN), "snapshot_dir": str(tmp_path / "snap"),
                         "min_gross_tonnage": None}}
    monkeypatch.setenv("MRV_MERGED_PATH", str(p))
    run(c)
    snap = load_snapshot(c)
    assert {"eedi_kind", "fuel_group", "cii_capacity", "hsc_proxy"} <= set(snap.columns)
    assert snap["eedi_kind"].dropna().isin(["EEDI"]).all()
    assert len(snap) == len(merged)


def test_vendor_pipeline_is_present_unmodified():
    """vendor/mrv_pipeline 은 팀 코드를 그대로 둔 것 → 핵심 파일이 있어야 한다."""
    for f in ("pipeline/run.py", "pipeline/rules_mrv.py", "mrv_reader.py", "README_pipeline.md"):
        assert (mrv_source.VENDOR / f).exists(), f
