# 파이썬 쪽 이미지: API 서버와 작업 명령(tasks.py)이 같은 이미지를 쓴다.
# 데이터(data/)와 산출물(artifacts/)은 이미지에 넣지 않고 compose 가 볼륨으로 붙인다 (이미지 하나로 어느 환경에서나 같은 코드).
FROM python:3.13-slim-bookworm

# lightgbm 이 쓰는 OpenMP 런타임
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8 PATH="/app/.venv/bin:$PATH"

# 의존성 먼저 (소스가 바뀌어도 이 층은 다시 만들지 않는다)
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev

COPY . .

# 기본 설정: 팀 전처리 + 공통잔차·회귀 v4 (config/mrv_pipeline.yaml). compose 에서 바꿀 수 있다
ENV SEA_CONFIG=config/mrv_pipeline.yaml
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
