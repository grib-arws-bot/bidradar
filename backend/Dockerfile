FROM python:3.12.7-slim-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 tesseract-ocr tesseract-ocr-kor tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml alembic.ini ./
COPY app ./app
COPY migrations ./migrations

# 코사인 유사도 매칭(2026-09-16, app/services/embeddings.py) — torch를 CPU 전용 휠로 먼저
# 설치한다(기본 PyPI 인덱스의 torch는 CUDA 라이브러리가 번들돼 수 GB로 훨씬 크다 — 이
# 서버엔 GPU가 없어 불필요). 아래 pip install .이 sentence-transformers를 설치할 때 이미
# 만족된 버전으로 보고 재설치하지 않는다.
RUN pip install --no-cache-dir torch==2.13.0 --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir .

# bge-m3 모델 가중치를 빌드 시점에 이미지 안에 미리 받아둔다 — CLAUDE.md "외부 요청은
# url_guard 경유" 원칙상 런타임에 Hugging Face Hub로 무가드 다운로드를 할 수 없다(prod는
# 이미지만 받아 교체할 뿐 빌드를 안 하므로, 여기서 못 받으면 영영 못 받는다).
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3')"

# 위에서 받아둔 캐시만 쓰고 런타임엔 Hugging Face Hub에 절대 접속하지 않는다(2026-09-16
# 실측 발견 — 오프라인 모드 없이는 매번 "최신 리비전 확인" 요청을 무가드로 내보내고
# 있었다, CLAUDE.md "외부 요청은 url_guard 경유 — 예외 없음"과 정면으로 어긋남). 빌드 시점
# 다운로드(위 RUN)는 이 ENV 적용 전이라 영향 없음.
ENV HF_HUB_OFFLINE=1
ENV TRANSFORMERS_OFFLINE=1

EXPOSE 3000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3000"]
