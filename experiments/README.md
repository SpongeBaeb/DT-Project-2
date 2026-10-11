# 실험 (A-1 ~ A-7)

사전 조사·비교 실험 코드는 여기에 `A-1_<주제>/` 처럼 둔다. 본류(`models/`)와 분리해 자유롭게 실험한다.

- 데이터는 `pipeline.run.load_snapshot(cfg)` 로 같은 스냅샷을 읽는다 (해시가 같으면 같은 데이터).
- 채택한 방법은 `models/` 에 Stage 로 옮기고 `config/` 에서 바꿔 끼운다 → `docs/PLUGIN_GUIDE.md`.
- 기존(확정 전) 코드도 일단 여기에 옮겨 두면 된다.
