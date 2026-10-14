"""AIS 수집 전용 프로세스: 모델 서버와 무관하게 aisstream 을 계속 받아 data/ais/state.json 에 모아 둔다.

실행: python -m api.ais_daemon [--hours 6] [--save-every 60]
- 서버(api.main)가 켜져 있어도 된다. 둘 다 같은 파일에 병합 저장한다.
- 키는 AISSTREAM_API_KEY (환경 변수 또는 프로젝트 루트 .env). 어디에도 출력하지 않는다.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import time

from api.ais import AisCollector, STATE_FILE
from pipeline.run import load_snapshot
from shared.config import load_config

log = logging.getLogger("ais.daemon")


async def run(hours: float, save_every: int) -> None:
    snap = load_snapshot(load_config())
    ais = AisCollector({int(i) for i in snap["imo"].dropna().unique()})
    ais.start()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows
            pass
    end = time.time() + hours * 3600 if hours > 0 else None
    log.info("수집 시작: 선박 %d척 대상, %s, 저장 %s", len(ais.known), f"{hours:g}시간" if end else "중단할 때까지", STATE_FILE)
    try:
        while not stop.is_set() and (end is None or time.time() < end):
            try:
                await asyncio.wait_for(stop.wait(), timeout=save_every)
            except asyncio.TimeoutError:
                pass
            ais.save()
            s = ais.stats()
            log.info("수신 %d건 · 매칭 %d척 · 위치 %d척 · 재접속 %d회 · %s", s["messages"], s["mapped_ships"], s["tracked_positions"], s["reconnects"],
                     "연결됨" if s["connected"] else "연결 끊김")
            if s["no_key"]:
                log.error("AISSTREAM_API_KEY 가 없어 종료합니다")
                break
    finally:
        await ais.stop()
        ais.save()
        s = ais.stats()
        log.info("종료: 매칭 %d척 · 위치 %d척 저장", s["mapped_ships"], s["tracked_positions"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=6.0, help="이 시간이 지나면 저장하고 종료 (0이면 계속)")
    ap.add_argument("--save-every", type=int, default=60, help="저장·기록 간격(초)")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    asyncio.run(run(a.hours, a.save_every))
