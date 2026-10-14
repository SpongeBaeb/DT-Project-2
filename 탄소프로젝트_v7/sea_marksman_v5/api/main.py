"""진단 API (6장, 7-1). [담당: 박준재]

실행: python tasks.py serve   →  http://localhost:8000/docs (자동 API 문서)

- 모델 파일은 artifacts/LATEST 버전을 시작할 때 한 번 읽는다.
- 계산은 shared.present + ModelBundle.run 을 그대로 부른다 (결과 표와 같은 코드 경로).
- 입력값은 저장하지 않는다 (로그에도 남기지 않는다).
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from contracts.api import (
    DiagnoseRequest, DiagnosisResult, HealthResponse, Meta, ShipInputs, WhatIfSpeedRequest, WhatIfSpeedResponse,
)
from api.ais import AisCollector
from contracts.tables import RESULT_TABLE
from models.bundle import ModelBundle
from models.physics import what_if_speed
from pipeline.run import load_snapshot
from publish.artifacts import latest_dir
from shared.config import load_config
from shared.present import PLACEHOLDER_IMO, frame_to_inputs, request_to_frame, row_to_result

STATE: dict = {}


def load_state(config_path: str | None = None) -> None:
    cfg = load_config(config_path)
    d = latest_dir()
    STATE.update(cfg=cfg, bundle=ModelBundle.load(d), snapshot=load_snapshot(cfg))


@asynccontextmanager
async def lifespan(app: FastAPI):
    if "bundle" not in STATE:
        load_state()
    # AIS 실시간 위치 (선택 기능): 키가 없으면 수집하지 않고 /ais 가 no_key 를 돌려준다
    ais = AisCollector({int(i) for i in STATE["snapshot"]["imo"].dropna().unique()})
    STATE["ais"] = ais
    if os.environ.get("SEA_AIS", "1") != "0":
        ais.start()
    try:
        yield
    finally:
        await ais.stop()


app = FastAPI(title="Sea Marksman API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=load_config()["api"]["cors_origins"], allow_methods=["GET", "POST"], allow_headers=["*"],
)


def _meta() -> dict:
    return STATE["bundle"].meta


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", model_version=_meta()["model_version"], data_hash=_meta()["data_hash"])


@app.get("/meta", response_model=Meta)
def meta() -> Meta:
    m = _meta()
    return Meta(model_version=m["model_version"], data_hash=m["data_hash"], result_table_version=RESULT_TABLE.version,
                ship_types=m["ship_types"], train_years=m["train_years"], created_at=m["created_at"])


@app.get("/ships/{imo}/inputs", response_model=ShipInputs)
def ship_inputs(imo: int) -> ShipInputs:
    snap = STATE["snapshot"]
    rows = snap[snap["imo"] == imo]
    if rows.empty:
        raise HTTPException(404, f"IMO {imo} 가 데이터에 없습니다")
    return frame_to_inputs(rows)


@app.get("/ais/status")
def ais_status() -> dict:
    ais = STATE.get("ais")
    return ais.stats() if ais else {"connected": False, "no_key": True}


@app.get("/ais/{imo}")
def ais_position(imo: int) -> dict:
    """선박의 최근 AIS 위치 (aisstream.io). 수신 전이면 status=waiting, 키가 없으면 no_key."""
    ais = STATE.get("ais")
    if ais is None:
        return {"imo": imo, "status": "no_key", "connected": False}
    return ais.lookup(imo)


@app.post("/diagnose", response_model=DiagnosisResult)
def diagnose(req: DiagnoseRequest) -> DiagnosisResult:
    bundle: ModelBundle = STATE["bundle"]
    if req.ship.ship_type not in bundle.meta["ship_types"]:
        raise HTTPException(422, f"선종 '{req.ship.ship_type}' 은 지원하지 않습니다. 가능: {bundle.meta['ship_types']}")
    frame = request_to_frame(req)
    try:
        res = bundle.run(frame)
    except (ValueError, KeyError) as e:
        raise HTTPException(422, f"진단할 수 없는 입력: {e}") from e
    last = res.iloc[-1]
    inputs_last = frame.sort_values("year").iloc[-1]
    return row_to_result(
        last, inputs_last, bundle.meta, STATE["cfg"]["thresholds"],
        imo_known=req.ship.imo is not None and req.ship.imo != PLACEHOLDER_IMO, mrv_confirmed=req.mrv_basis_confirmed,
    )


@app.post("/whatif/speed", response_model=WhatIfSpeedResponse)
def whatif_speed(req: WhatIfSpeedRequest) -> WhatIfSpeedResponse:
    shares = STATE["cfg"]["physics"]["main_engine_share"]
    share = req.main_engine_share or shares.get(req.ship_type)
    if share is None:
        raise HTTPException(422, f"선종 '{req.ship_type}' 의 주기관 비중 기본값이 없습니다. main_engine_share 를 넣어 주세요")
    after = what_if_speed(req.sea_eff_kg_nm, req.speed_change_pct, share)
    return WhatIfSpeedResponse(
        sea_eff_before=req.sea_eff_kg_nm, sea_eff_after=after, change_pct=(after / req.sea_eff_kg_nm - 1) * 100,
        main_engine_share=share, method="physics_rule",
        note="물리 규칙 기반 추정 (회귀 계수 아님). 주기관 거리당 연료 ∝ 속력², 보조기관 ∝ 1/속력",
    )
