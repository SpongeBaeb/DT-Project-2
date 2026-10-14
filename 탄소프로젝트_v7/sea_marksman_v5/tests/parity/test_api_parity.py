"""결과 일치 테스트 (7-5②): 데이터에 있는 배를 API 에 넣으면 결과 표·정적 JSON 과 같아야 한다 (오차 1e-9)."""
import math

import pytest
from fastapi.testclient import TestClient

import api.main as api
from shared.present import row_to_result

TOL = 1e-9


@pytest.fixture(scope="module")
def client(cfg, bundle, snapshot):
    api.STATE.clear()
    api.STATE.update(cfg=cfg, bundle=bundle, snapshot=snapshot)
    return TestClient(api.app)


def _close(a, b, path=""):
    if isinstance(a, dict):
        assert a.keys() == b.keys(), path
        for k in a:
            _close(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list):
        assert len(a) == len(b), path
        for i, (x, y) in enumerate(zip(a, b)):
            _close(x, y, f"{path}[{i}]")
    elif isinstance(a, float) and isinstance(b, float):
        assert math.isclose(a, b, rel_tol=TOL, abs_tol=TOL), f"{path}: {a} != {b}"
    else:
        assert a == b, f"{path}: {a!r} != {b!r}"


def _static(results, snapshot, bundle, cfg, imo):
    r = results[results["imo"] == imo].iloc[-1]
    s = snapshot[(snapshot["imo"] == imo) & (snapshot["year"] == r["year"])].iloc[0]
    return row_to_result(r, s, bundle.meta, cfg["thresholds"]).model_dump(mode="json")


def test_api_equals_result_table(client, results, snapshot, bundle, cfg):
    for imo in snapshot["imo"].drop_duplicates().sample(25, random_state=1):
        inputs = client.get(f"/ships/{imo}/inputs").json()
        got = client.post("/diagnose", json={**inputs, "mrv_basis_confirmed": True}).json()
        want = _static(results, snapshot, bundle, cfg, imo)
        got["checks"] = [c for c in got["checks"] if c["rule"] != "EU MRV 보고 기준 값"]
        _close(got, want, f"imo={imo}")


def test_single_year_without_imo(client, snapshot):
    imo = int(snapshot["imo"].iloc[0])
    inputs = client.get(f"/ships/{imo}/inputs").json()
    inputs["ship"]["imo"] = None
    inputs["years"] = inputs["years"][-1:]
    r = client.post("/diagnose", json=inputs)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["imo"] is None
    assert body["position"]["n_years"] == 1 and body["position"]["note"]
    assert any(c["rule"] == "EU MRV 보고 기준 값" and not c["ok"] for c in body["checks"])


def test_rejects_bad_input(client):
    r = client.post("/diagnose", json={"ship": {"ship_type": "tanker", "dwt": -1, "build_year": 2010}, "years": []})
    assert r.status_code == 422


def test_unknown_type_is_422(client, snapshot):
    imo = int(snapshot["imo"].iloc[0])
    inputs = client.get(f"/ships/{imo}/inputs").json()
    inputs["ship"]["ship_type"] = "submarine"
    assert client.post("/diagnose", json=inputs).status_code == 422


def test_whatif_speed(client):
    r = client.post("/whatif/speed", json={"ship_type": "tanker", "sea_eff_kg_nm": 400, "speed_change_pct": -10}).json()
    assert r["sea_eff_after"] < 400 and r["method"] == "physics_rule"
