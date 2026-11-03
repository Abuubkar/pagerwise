# The embedding and reranker weights, downloaded once. CI tags it with a hash of the model names in settings.py and
# the fastembed version, and rebuilds it only when that tag is missing, so service builds skip a ~0.6 GB download.
# Apps that embed or rerank (api, consumer, indexer) use it as their runtime base: see python.Dockerfile.
FROM python:3.13-slim-trixie@sha256:ae14d4ce8771606477a81446e7ef429edd6762305fc50c84507c1041fa8285d1
COPY --from=ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 /uv /bin/

ARG FASTEMBED_VERSION
ARG EMBEDDING_MODELS
ARG RERANKER_MODEL
ENV FASTEMBED_CACHE_PATH=/models
RUN test -n "$FASTEMBED_VERSION" && test -n "$EMBEDDING_MODELS" && test -n "$RERANKER_MODEL" \
 && uv run --no-project --python /usr/local/bin/python --with "fastembed==${FASTEMBED_VERSION}" python -c "\
from fastembed import TextEmbedding; \
from fastembed.rerank.cross_encoder import TextCrossEncoder; \
[TextEmbedding(model_name=m) for m in '${EMBEDDING_MODELS}'.split()]; \
TextCrossEncoder(model_name='${RERANKER_MODEL}')" \
 && rm -rf /root/.cache/uv /bin/uv \
 && chmod -R a+rX /models
# Everything is in /models: never reach Hugging Face at runtime.
ENV HF_HUB_OFFLINE=1
