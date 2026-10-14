"""AIS 실시간 위치 수집 (aisstream.io). [화면 보조 기능: 진단 모델과 무관]

- 서버가 aisstream 에 한 번만 접속해 두고, 우리 데이터의 선박(IMO 목록)만 메모리에 모은다.
- aisstream 은 MMSI 기준이므로 ShipStaticData(IMO·MMSI 함께 옴, 배마다 약 6분에 한 번)로 IMO→MMSI 표를 만든다.
- 표와 마지막 위치는 data/ais/state.json 에 저장해 다음 실행 때 바로 쓴다. 위치는 수신 시각과 함께 보여 주고 오래되면 표시한다.
- 키(AISSTREAM_API_KEY)는 환경 변수 또는 프로젝트 루트 .env 에서 읽고 어디에도 출력하지 않는다.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
from pathlib import Path

log = logging.getLogger("ais")

WS_URL = "wss://stream.aisstream.io/v0/stream"
ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "data" / "ais" / "state.json"
ENV_FILES = [ROOT / ".env", ROOT.parent / ".env"]
STALE_AFTER_S = 6 * 3600  # 6시간 넘게 수신이 없으면 '오래됨'으로 표시
SAVE_EVERY_S = 300

NAV_STATUS = {
    0: "기관 항해 중", 1: "정박(닻)", 2: "조종 불능", 3: "조종 제한", 4: "흘수 제약", 5: "계류", 6: "좌주", 7: "어로 중",
    8: "범주 항해 중", 11: "예선 작업", 12: "밀기·끌기", 14: "비상 신호", 15: "정의되지 않음",
}


def read_key() -> str | None:
    key = os.environ.get("AISSTREAM_API_KEY")
    if key:
        return key.strip()
    for f in ENV_FILES:
        if f.exists():
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.startswith("AISSTREAM_API_KEY="):
                    return line.split("=", 1)[1].strip() or None
    return None


class AisCollector:
    def __init__(self, known_imos: set[int]):
        self.known = known_imos
        self.imo_to_mmsi: dict[int, int] = {}
        self.mmsi_to_imo: dict[int, int] = {}
        self.pos: dict[int, dict] = {}  # mmsi → 마지막 위치
        self.info: dict[int, dict] = {}  # imo → 정적 정보(목적지·도착 예정·흘수·AIS 선명)
        self.connected = False
        self.n_msgs = 0
        self.n_reconnects = 0
        self.last_msg_at: float | None = None
        self.started_at = time.time()
        self.no_key = False
        self._task: asyncio.Task | None = None
        self._load()

    # ── 저장·복원 ──
    def _load(self) -> None:
        try:
            d = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.imo_to_mmsi = {int(k): int(v) for k, v in d.get("imo_to_mmsi", {}).items() if int(k) in self.known}
        self.mmsi_to_imo = {m: i for i, m in self.imo_to_mmsi.items()}
        self.pos = {int(k): v for k, v in d.get("pos", {}).items() if int(k) in self.mmsi_to_imo}
        self.info = {int(k): v for k, v in d.get("info", {}).items() if int(k) in self.known}

    def _read_disk(self) -> dict:
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def save(self) -> None:
        """디스크 값과 병합해 저장한다 (서버와 수집 전용 프로세스가 같은 파일을 쓸 수 있다). 더 최근 값이 이긴다."""
        d = self._read_disk()
        try:
            for k, v in d.get("imo_to_mmsi", {}).items():
                imo, mmsi = int(k), int(v)
                if imo in self.known and imo not in self.imo_to_mmsi:
                    self.imo_to_mmsi[imo] = mmsi
            self.mmsi_to_imo = {m: i for i, m in self.imo_to_mmsi.items()}
            for k, v in d.get("pos", {}).items():
                m = int(k)
                if m in self.mmsi_to_imo and v.get("at", 0) > self.pos.get(m, {}).get("at", 0):
                    self.pos[m] = v
            for k, v in d.get("info", {}).items():
                i = int(k)
                if i in self.known and v.get("at", 0) > self.info.get(i, {}).get("at", 0):
                    self.info[i] = v
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = STATE_FILE.with_suffix(f".{os.getpid()}.tmp")
            tmp.write_text(json.dumps({"saved_at": time.time(), "imo_to_mmsi": self.imo_to_mmsi, "pos": self.pos, "info": self.info},
                                      ensure_ascii=False), encoding="utf-8")
            tmp.replace(STATE_FILE)
        except (OSError, ValueError, TypeError) as e:
            log.warning("AIS 상태 저장 실패: %s", e)

    # ── 수신 ──
    def _on_message(self, m: dict) -> None:
        md = m.get("MetaData")
        if not md:
            return
        t = m.get("MessageType")
        mmsi = int(md.get("MMSI") or 0)
        now = time.time()
        self.n_msgs += 1
        self.last_msg_at = now
        if t == "ShipStaticData":
            s = (m.get("Message") or {}).get("ShipStaticData") or {}
            imo = int(s.get("ImoNumber") or 0)
            if imo in self.known and mmsi:
                old = self.imo_to_mmsi.get(imo)
                if old != mmsi:
                    if old is not None:
                        self.mmsi_to_imo.pop(old, None)
                    self.imo_to_mmsi[imo] = mmsi
                    self.mmsi_to_imo[mmsi] = imo
                eta = s.get("Eta") or {}
                self.info[imo] = {
                    "name": (s.get("Name") or "").strip() or None,
                    "destination": (s.get("Destination") or "").strip() or None,
                    "eta": {k: eta.get(k) for k in ("Month", "Day", "Hour", "Minute")} if eta.get("Month") else None,
                    "draught": s.get("MaximumStaticDraught") or None,
                    "at": now,
                }
        elif t == "PositionReport":
            if mmsi in self.mmsi_to_imo:
                p = (m.get("Message") or {}).get("PositionReport") or {}
                lat, lon = p.get("Latitude"), p.get("Longitude")
                if lat is None or lon is None or abs(lat) > 90 or abs(lon) > 180:
                    return
                self.pos[mmsi] = {
                    "lat": lat, "lon": lon, "sog": p.get("Sog"), "cog": p.get("Cog"), "hdg": p.get("TrueHeading"),
                    "nav": p.get("NavigationalStatus"), "at": now,
                }

    async def _run(self) -> None:
        import websockets

        key = read_key()
        if not key:
            self.no_key = True
            log.warning("AISSTREAM_API_KEY 가 없어 AIS 수집을 시작하지 않습니다")
            return
        backoff = 2.0
        last_save = time.time()
        while True:
            try:
                async with websockets.connect(WS_URL, max_size=None, ping_interval=20, ping_timeout=30) as ws:
                    await ws.send(json.dumps({
                        "APIKey": key, "BoundingBoxes": [[[-90, -180], [90, 180]]],
                        "FilterMessageTypes": ["PositionReport", "ShipStaticData"],
                    }))
                    self.connected = True
                    backoff = 2.0
                    async for raw in ws:
                        try:
                            m = json.loads(raw)
                        except ValueError:
                            continue
                        if "error" in m:
                            log.warning("aisstream 오류 응답: %s", str(m.get("error"))[:120])
                            break
                        self._on_message(m)
                        if time.time() - last_save > SAVE_EVERY_S:
                            self.save()
                            last_save = time.time()
            except asyncio.CancelledError:
                self.connected = False
                self.save()
                raise
            except Exception as e:  # 끊김은 흔하다: 지수 백오프 + 지터로 다시 접속
                log.warning("aisstream 연결 끊김 (%s). %.0f초 뒤 재접속", type(e).__name__, backoff)
            self.connected = False
            self.n_reconnects += 1
            await asyncio.sleep(backoff + random.random())
            backoff = min(backoff * 2, 60.0)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    # ── 조회 ──
    def lookup(self, imo: int) -> dict:
        now = time.time()
        base = {"imo": imo, "connected": self.connected}
        if self.no_key:
            return {**base, "status": "no_key"}
        mmsi = self.imo_to_mmsi.get(imo)
        if mmsi is None:
            return {**base, "status": "waiting", "listening_s": round(now - self.started_at)}
        base["mmsi"] = mmsi
        info = self.info.get(imo) or {}
        base.update({"name": info.get("name"), "destination": info.get("destination"), "eta": info.get("eta"), "draught": info.get("draught")})
        p = self.pos.get(mmsi)
        if not p:
            return {**base, "status": "no_position"}
        age = now - p["at"]
        nav = p.get("nav")
        return {
            **base, "status": "stale" if age > STALE_AFTER_S else "ok", "age_s": round(age),
            "lat": p["lat"], "lon": p["lon"],
            "sog": p["sog"] if p.get("sog") is not None and p["sog"] < 102.3 else None,
            "cog": p["cog"] if p.get("cog") is not None and p["cog"] < 360 else None,
            "heading": p["hdg"] if p.get("hdg") is not None and p["hdg"] < 360 else None,
            "nav_status": NAV_STATUS.get(nav, None) if nav is not None else None,
            "received_at": p["at"],
        }

    def stats(self) -> dict:
        now = time.time()
        return {
            "connected": self.connected, "no_key": self.no_key, "messages": self.n_msgs, "reconnects": self.n_reconnects,
            "mapped_ships": len(self.imo_to_mmsi), "tracked_positions": len(self.pos), "known_ships": len(self.known),
            "last_message_s": None if self.last_msg_at is None else round(now - self.last_msg_at),
            "uptime_s": round(now - self.started_at),
            "examples": [self.mmsi_to_imo[m] for m in list(self.pos)[:6] if m in self.mmsi_to_imo],
        }
