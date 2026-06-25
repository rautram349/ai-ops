"""Embedding model factory for semantic search."""

from __future__ import annotations

from functools import lru_cache

from langchain_openai import AzureOpenAIEmbeddings

from backend.core.config import settings


@lru_cache(maxsize=1)
def get_embeddings_model() -> AzureOpenAIEmbeddings:
    """Return a cached AzureOpenAIEmbeddings instance pointed at EPAM DIAL."""
    return AzureOpenAIEmbeddings(
        azure_deployment=settings.epam_dial_embedding_deployment,
        azure_endpoint=settings.epam_dial_endpoint,
        api_key=settings.epam_dial_api_key,  # type: ignore[arg-type]
        api_version=settings.epam_dial_api_version,
    )


async def embed_text(text: str) -> list[float]:
    """Generate an embedding vector for the given text."""
    model = get_embeddings_model()
    vectors = await model.aembed_documents([text])
    return vectors[0]
