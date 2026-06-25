"""GraphRunner protocol and default implementation.

Decouples ChatService from the concrete ai_ops_engine graph builder,
making the service testable without a live LLM.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Protocol, runtime_checkable


@runtime_checkable
class GraphRunner(Protocol):
    async def run(self, user_query: str, **kwargs: Any) -> dict[str, Any]: ...

    async def stream(
        self, initial_state: dict[str, Any]
    ) -> AsyncIterator[dict[str, Any]]: ...


class DefaultGraphRunner:
    async def run(self, user_query: str, **kwargs: Any) -> dict[str, Any]:
        from ai_ops_engine.graph.builder import run_graph

        return await run_graph(user_query, **kwargs)

    async def stream(
        self, initial_state: dict[str, Any]
    ) -> AsyncIterator[dict[str, Any]]:
        from ai_ops_engine.graph.builder import stream_graph_events

        async for event in stream_graph_events(initial_state):
            yield event
