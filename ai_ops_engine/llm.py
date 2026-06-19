"""LLM factory for the ai_ops_engine.

Returns a LangChain-compatible chat model backed by EPAM DIAL
(AzureOpenAI proxy).  All config is read from environment variables /
``.env`` via the shared ``Settings`` singleton.

Usage::

    from ai_ops_engine.llm import get_llm
    llm = get_llm()
    response = await llm.ainvoke("Hello")
"""

from __future__ import annotations

from functools import lru_cache

from langchain_openai import AzureChatOpenAI

from backend.core.config import settings


@lru_cache(maxsize=1)
def get_llm() -> AzureChatOpenAI:
    """Return a cached AzureChatOpenAI instance pointed at EPAM DIAL."""
    return AzureChatOpenAI(
        openai_api_version=settings.epam_dial_api_version,
        azure_deployment=settings.epam_dial_deployment,
        azure_endpoint=settings.epam_dial_endpoint,
        api_key=settings.epam_dial_api_key,  # type: ignore[arg-type]
        temperature=settings.llm_temperature,
        request_timeout=120,
        max_retries=1,
    )
