"""The local embedding model. Loaded once per process: loading the ONNX model takes about a second."""

from functools import cache

from fastembed import TextEmbedding

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
    past 512 tokens; it's also a close stand-in for the chat model's count on English text."""
    return _model().token_count(text)
