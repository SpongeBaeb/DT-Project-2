# 실험 (A-1 ~ A-7)

사전 조사·비교 실험 코드는 여기에 `A-1_<주제>/` 처럼 둔다. 본류(`models/`)와 분리해 자유롭게 실험한다.

- 데이터는 `pipeline.run.load_snapshot(cfg)` 로 같은 스냅샷을 읽는다 (해시가 같으면 같은 데이터).
- 채택한 방법은 `models/` 에 Stage 로 옮기고 `config/` 에서 바꿔 끼운다 → `docs/PLUGIN_GUIDE.md`.
- 기존(확정 전) 코드도 일단 여기에 옮겨 두면 된다.

## 보관된 실험
- `A-0_common_residual/` — 배성우 님 공통잔차 원본 (스크립트, 계수표, 요약, 설명서). 원본은 `mrv_pipeline` 의 `mrv_merged.parquet` 를 읽는 구조라 이 레포에서는 실행하지 않고 참고용이다. 본류로 옮긴 것은 `models/common/common_residual.py`.
- `A-1_forecast_features/` — 회귀 v4 예측 이식 검증. `verify_features.py`(피처 36개를 팀 `features_*.csv` 와 대조), `team_reference_run.py`(팀 원본 코드를 이 환경에서 실행해 기준 예측 생성), `verify_forecast.py`(이식한 예측을 기준과 대조, 판정은 '잡음 바닥' 이내). 필요한 입력은 회귀 묶음(`regression_v4_final_*`)의 스냅샷 `3183d290` 과 `v1` 폴더.
