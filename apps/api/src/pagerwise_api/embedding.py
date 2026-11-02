"""The local models: the embedding model and the reranker. Each is loaded once per process, on first use."""

from functools import cache

from fastembed import TextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder

from pagerwise_api.settings import settings


@cache
def _model() -> TextEmbedding:
    return TextEmbedding(model_name=settings.embedding_model)


def embed_passages(texts: list[str]) -> list[list[float]]:
    return [v.tolist() for v in _model().passage_embed(texts)]


def embed_query(text: str) -> list[float]:
    return next(iter(_model().query_embed(text))).tolist()


def count_tokens(text: str) -> int:
    """Tokens as the embedding model counts them. Chunks are sized with this because bge-small ignores anything
    past 512 tokens; it's also a close stand-in for the chat model's count on English text (the prompt budget).

    fastembed's token_count stops at that same 512-token window, so a long prompt would be undercounted. Counting
    line by line is exact (WordPiece has no token for a line break) unless one line alone passes 512 tokens."""
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return 0
    # Each line is encoded with its own [CLS] and [SEP]; keep one pair, as a single encode would.
    return _model().token_count(lines) - 2 * (len(lines) - 1)


@cache
def _reranker() -> TextCrossEncoder:
    return TextCrossEncoder(model_name=settings.reranker_model)


def rerank(query: str, texts: list[str]) -> list[float]:
    """Relevance of each text to the query, read together by a cross-encoder. Higher is better; only the order
    means anything (scores are raw logits, not probabilities)."""
    return [float(s) for s in _reranker().rerank(query, texts, batch_size=len(texts) or 1)]

