"""AIS 수집기: 메시지 처리와 조회 상태 (네트워크 없이)."""
import time

from api.ais import AisCollector


def _static(imo: int, mmsi: int, dest: str = "ROTTERDAM") -> dict:
    return {"MessageType": "ShipStaticData", "MetaData": {"MMSI": mmsi},
            "Message": {"ShipStaticData": {"ImoNumber": imo, "Name": "TEST SHIP ", "Destination": dest, "Eta": {"Month": 10, "Day": 13, "Hour": 5, "Minute": 0},
                                           "MaximumStaticDraught": 9.6}}}


def _pos(mmsi: int, lat=55.6, lon=21.1, sog=12.3, cog=25.0, hdg=24, nav=0) -> dict:
    return {"MessageType": "PositionReport", "MetaData": {"MMSI": mmsi},
            "Message": {"PositionReport": {"Latitude": lat, "Longitude": lon, "Sog": sog, "Cog": cog, "TrueHeading": hdg, "NavigationalStatus": nav}}}


def make(monkeypatch, tmp_path) -> AisCollector:
    monkeypatch.setattr("api.ais.STATE_FILE", tmp_path / "state.json")
    return AisCollector({9776767, 8913423})


def test_waiting_until_static_data_seen(monkeypatch, tmp_path):
    c = make(monkeypatch, tmp_path)
    assert c.lookup(9776767)["status"] == "waiting"
    c._on_message(_pos(111))  # 아직 모르는 MMSI 위치는 버린다
    assert not c.pos


def test_position_after_mapping(monkeypatch, tmp_path):
    c = make(monkeypatch, tmp_path)
    c._on_message(_static(9776767, 636000001))
    assert c.lookup(9776767)["status"] == "no_position"
    c._on_message(_pos(636000001))
    r = c.lookup(9776767)
    assert r["status"] == "ok" and r["mmsi"] == 636000001
    assert (r["lat"], r["lon"], r["sog"], r["heading"]) == (55.6, 21.1, 12.3, 24)
    assert r["name"] == "TEST SHIP" and r["destination"] == "ROTTERDAM" and r["nav_status"] == "기관 항해 중"


def test_unknown_imo_is_ignored(monkeypatch, tmp_path):
    c = make(monkeypatch, tmp_path)
    c._on_message(_static(1234567, 222))
    assert not c.imo_to_mmsi


def test_invalid_values_become_none(monkeypatch, tmp_path):
    c = make(monkeypatch, tmp_path)
    c._on_message(_static(8913423, 354540000))
    c._on_message(_pos(354540000, sog=102.3, cog=360, hdg=511))  # AIS '값 없음' 코드
    r = c.lookup(8913423)
    assert r["sog"] is None and r["cog"] is None and r["heading"] is None
    c._on_message(_pos(354540000, lat=91.0))  # 좌표 범위 밖은 갱신하지 않는다
    assert c.lookup(8913423)["lat"] == 55.6


def test_stale_and_persistence(monkeypatch, tmp_path):
    c = make(monkeypatch, tmp_path)
    c._on_message(_static(8913423, 354540000))
    c._on_message(_pos(354540000))
    c.pos[354540000]["at"] = time.time() - 7 * 3600
    assert c.lookup(8913423)["status"] == "stale"
    c.save()
    c2 = make(monkeypatch, tmp_path)  # 다음 실행: 표와 마지막 위치를 복원
    assert c2.lookup(8913423)["status"] == "stale" and c2.lookup(8913423)["mmsi"] == 354540000


def test_no_key(monkeypatch, tmp_path):
    c = make(monkeypatch, tmp_path)
    c.no_key = True
    assert c.lookup(9776767)["status"] == "no_key"


def test_merge_save_keeps_other_process_data(monkeypatch, tmp_path):
    """서버와 수집 전용 프로세스가 같은 파일에 저장해도 서로의 값이 사라지지 않는다."""
    a = make(monkeypatch, tmp_path)
    b = make(monkeypatch, tmp_path)
    a._on_message(_static(9776767, 111111111))
    a._on_message(_pos(111111111, lat=10.0))
    a.save()
    b._on_message(_static(8913423, 222222222))
    b._on_message(_pos(222222222, lat=20.0))
    b.save()  # a 가 저장한 값과 병합
    assert b.lookup(9776767)["lat"] == 10.0 and b.lookup(8913423)["lat"] == 20.0
    c = make(monkeypatch, tmp_path)
    assert c.lookup(9776767)["mmsi"] == 111111111 and c.lookup(8913423)["mmsi"] == 222222222
