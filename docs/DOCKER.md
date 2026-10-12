# 도커로 실행하기

어느 컴퓨터에서나 같은 환경(파이썬 3.13 + `uv.lock` 고정 버전, Node 22, nginx)으로 웹과 API 를 켠다.

## 켜기
```bash
docker compose up --build        # 웹 http://localhost:8080
```
- 웹 하나만 바깥에 열린다. API 는 웹이 `/api/` 로 넘겨 주므로 따로 열 필요가 없다 (API 문서: `http://localhost:8080/api/docs`).
- 포트를 바꾸려면 `WEB_PORT=9000 docker compose up`.
- 같은 네트워크의 다른 컴퓨터는 `http://<이 컴퓨터 IP>:8080` 으로 들어온다 (Windows 방화벽에서 8080 허용 필요).
- 끄기: `docker compose down`

## 데이터와 산출물은 이미지에 없다
이미지에는 코드만 들어 있고, 아래 폴더를 볼륨으로 붙인다 (git 에 안 올리는 폴더).

| 폴더 | 쓰임 |
|---|---|
| `data/snapshots/` | 배·연도 표 (API 가 한 척 진단·불러오기에 씀, 읽기 전용) |
| `artifacts/` | 모델 파일·결과 표 (API 가 시작할 때 `LATEST` 를 읽음) |
| `web/public/data/` | 웹이 읽는 선박별 JSON |

산출물이 없는 새 컴퓨터에서는 작업 이미지로 먼저 만든다 (MRV 엑셀은 `data/raw/` 에 둬야 함).
```bash
docker compose run --rm tools python tasks.py pipeline
docker compose run --rm tools python tasks.py build
docker compose up --build
```
`tools` 는 평소에는 안 켜지는 작업용 서비스다 (`tasks.py` 의 어느 명령이든 같은 식으로).

## 설정
- API 컨테이너는 `SEA_CONFIG=config/mrv_pipeline.yaml` 로 설정을 고른다. 다른 설정은 `docker-compose.yml` 의 `environment` 에서 바꾼다 (환경변수 `SEA_CONFIG` 는 `--config` 가 없을 때만 쓰임).
- 모델 파일(joblib)은 만든 코드·라이브러리와 같은 버전에서만 안전하게 읽힌다. 이미지는 `uv.lock` 으로 버전을 고정한다.

## 알려진 한계
- 한 척 진단(`/diagnose`)은 아직 새 모델의 입력 열(설계 효율·선형 보정·평균 적재 등)을 받지 못해 결과 표와 값이 다르다. 배 전체 표와 웹의 선박 상세(JSON)는 결과 표 값이다.
