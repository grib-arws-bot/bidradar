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
#
# 2026-09-17 — 이 레이어가 4.57GB나 나가서 원인을 봤다: BAAI/bge-m3의 main 리비전엔
# pytorch_model.bin만 정식으로 커밋돼 있고, model.safetensors는 허깅페이스가 "safetensors
# 없는 저장소"에 대해 온라인에서만 조회되는 별도 리비전(자동 변환본)으로 제공하는 것이었다.
# use_safetensors=False로 로딩 자체는 bin만 쓰게 강제했지만(오프라인 런타임에서 실제
# 컨테이너 실행으로 검증함), sentence-transformers 내부 로딩 과정이 이 값과 무관하게 그
# 자동변환본을 여전히 캐시에 받는다 — huggingface_hub의 공식 캐시 정리 API
# (scan_cache_dir().delete_revisions())로 지워봐도 심볼릭 링크만 지워지고 실제 blob
# 파일(2.2GB)이 고아 상태로 레이어에 남는 걸 확인했다. 그래서 라이브러리 동작에 기대지
# 않고 파일시스템 레벨에서 직접 정리한다 — 실제로 쓰는 pytorch_model.bin이 가리키는
# blob 하나만 남기고, 그 외 50MB 넘는 blob은 전부 지운다(같은 RUN 안에서 지워야 최종
# 이미지 레이어에 안 남는다).
RUN python -c "\
from huggingface_hub import snapshot_download; \
snapshot_download('BAAI/bge-m3', ignore_patterns=['*.msgpack', '*.h5', '*.onnx', 'onnx/*', 'openvino/*', 'colbert_linear.pt', 'sparse_linear.pt']); \
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('BAAI/bge-m3', model_kwargs={'use_safetensors': False})" \
    && KEEP="$(readlink -f /root/.cache/huggingface/hub/models--BAAI--bge-m3/snapshots/*/pytorch_model.bin)" \
    && find /root/.cache/huggingface/hub/models--BAAI--bge-m3/blobs -type f -size +50M ! -samefile "$KEEP" -delete

# 위에서 받아둔 캐시만 쓰고 런타임엔 Hugging Face Hub에 절대 접속하지 않는다(2026-09-16
# 실측 발견 — 오프라인 모드 없이는 매번 "최신 리비전 확인" 요청을 무가드로 내보내고
# 있었다, CLAUDE.md "외부 요청은 url_guard 경유 — 예외 없음"과 정면으로 어긋남). 빌드 시점
# 다운로드(위 RUN)는 이 ENV 적용 전이라 영향 없음.
ENV HF_HUB_OFFLINE=1
ENV TRANSFORMERS_OFFLINE=1

EXPOSE 3000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3000"]
