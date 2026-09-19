# syntax=docker/dockerfile:1.7
FROM python:3.12.7-slim-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 tesseract-ocr tesseract-ocr-kor tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# 2026-09-18 — torch·sentence-transformers 설치와 bge-m3 모델 다운로드를 COPY pyproject.toml
# 보다 앞으로 옮겼다. 원래는 COPY 다음에 있었는데, 이 셋 다 pyproject.toml 내용과 무관한데도
# (torch 버전·모델명이 여기 하드코딩돼 있다) Docker가 레이어를 순서대로 무효화하는 탓에
# pyproject.toml을 조금만 고쳐도(dev 의존성 추가처럼 실제 이미지에 안 들어가는 항목이라도)
# 이 무거운 레이어(torch 수백MB + 모델 2GB대)가 통째로 재실행됐다(2026-09-18 실측 —
# pytest-xdist 의존성 한 줄 추가만으로 이미지 빌드가 24분+ 걸림). 의사결정_로그 169번 후속
# (project_deploy_speed_ideas_20260917).
#
# --mount=type=cache로 pip 다운로드 캐시를 레이어 밖에 둔다 — 이 값을 바꿀 때(torch
# 버전 등) 레이어가 다시 실행되더라도 이미 받은 휠은 캐시에서 재사용하고, 캐시 자체는
# 최종 이미지에 안 남는다.
#
# sentence-transformers 버전 범위는 backend/pyproject.toml의 [project.dependencies]와
# 반드시 일치해야 한다 — 다르면 아래 COPY 이후 `pip install .`이 다른 버전으로 다시 설치를
# 시도하면서 여기서 미리 설치해둔 효과가 사라진다. pyproject.toml에서 이 버전을 바꾸면
# 여기도 같이 바꿀 것.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install torch==2.13.0 --index-url https://download.pytorch.org/whl/cpu
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install "sentence-transformers>=6.0,<6.1"

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
#
# 2026-09-19 — Dockerfile 재배치 검증 빌드에서 이미지가 6.06GB→9.66GB로 다시 커진 걸
# 발견해 원인을 봤다: huggingface_hub가 그 사이 버전이 올라가며 blob 저장 위치를
# 모델별 디렉터리(models--BAAI--bge-m3/blobs/)에서 전역 공유 디렉터리(hub/blobs/,
# 해시 앞 2글자로 샤딩)로 바꿨다 — 아래 find가 여전히 모델별 디렉터리만 뒤져서 실제
# 2.2GB짜리 중복 blob 두 개(pytorch_model.bin용 하나, model.safetensors 자동변환본
# 하나)가 있는 hub/blobs/를 못 보고 그냥 통과시키고 있었다. 탐색 범위를 상위
# hub/ 디렉터리 전체로 넓혀 신구 레이아웃 둘 다 커버한다(이 이미지엔 bge-m3 하나만
# 받으므로 범위를 넓혀도 다른 모델 blob과 섞일 위험 없음). $KEEP은 readlink -f가
# 심볼릭 링크 체인을 끝까지 따라가서 구하므로 레이아웃 변화와 무관하게 그대로 유효.
RUN python -c "\
from huggingface_hub import snapshot_download; \
snapshot_download('BAAI/bge-m3', ignore_patterns=['*.msgpack', '*.h5', '*.onnx', 'onnx/*', 'openvino/*', 'colbert_linear.pt', 'sparse_linear.pt']); \
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('BAAI/bge-m3', model_kwargs={'use_safetensors': False})" \
    && KEEP="$(readlink -f /root/.cache/huggingface/hub/models--BAAI--bge-m3/snapshots/*/pytorch_model.bin)" \
    && find /root/.cache/huggingface/hub -type f -size +50M ! -samefile "$KEEP" -delete

COPY pyproject.toml alembic.ini ./
COPY app ./app
COPY migrations ./migrations

# torch·sentence-transformers는 위에서 이미 만족된 버전으로 설치돼 있어 재설치하지 않는다 —
# 나머지(가벼운) 의존성만 새로 설치된다. 여기도 캐시 마운트를 써서, pyproject.toml의 실제
# 의존성이 바뀌어 이 레이어가 재실행되는 경우에도 이미 받은 휠은 네트워크 재다운로드 없이
# 재사용한다.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install .

# 위에서 받아둔 캐시만 쓰고 런타임엔 Hugging Face Hub에 절대 접속하지 않는다(2026-09-16
# 실측 발견 — 오프라인 모드 없이는 매번 "최신 리비전 확인" 요청을 무가드로 내보내고
# 있었다, CLAUDE.md "외부 요청은 url_guard 경유 — 예외 없음"과 정면으로 어긋남). 빌드 시점
# 다운로드(위 RUN)는 이 ENV 적용 전이라 영향 없음.
ENV HF_HUB_OFFLINE=1
ENV TRANSFORMERS_OFFLINE=1

EXPOSE 3000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3000"]
