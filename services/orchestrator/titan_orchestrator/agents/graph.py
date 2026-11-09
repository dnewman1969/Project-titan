"""Generic AgentRuntime LangGraph (M6.T3)."""

from __future__ import annotations

from typing import TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from titan_models.fake import FakeProvider
from titan_models.types import ChatMessage, GenerationParams
from titan_orchestrator.agents.context import build_context


class AgentGraphState(TypedDict, total=False):
    context: str
    intent: str
    reply: str


async def _perceive(state: AgentGraphState) -> AgentGraphState:
    return {"context": state.get("context", "")}


async def _decide(state: AgentGraphState, provider: FakeProvider, model: str) -> AgentGraphState:
    prompt = build_context(
        system_prompt=state.get("context", ""),
        tasks=[],
        blackboard=[],
        world_state=None,
        chat_lines=[],
        memories=[],
    )
    result = await provider.chat(
        model,
        [ChatMessage(role="user", content=prompt)],
        GenerationParams(max_tokens=64, temperature=0.2),
    )
    return {"intent": "speak" if result.text else "none", "reply": result.text}


def build_agent_graph(
    provider: FakeProvider, *, model: str = "fake:small"
) -> StateGraph[AgentGraphState, None, AgentGraphState, AgentGraphState]:
    graph = StateGraph(AgentGraphState)
    graph.add_node("perceive", _perceive)

    async def decide(state: AgentGraphState) -> AgentGraphState:
        return await _decide(state, provider, model)

    graph.add_node("decide", decide)
    graph.add_edge(START, "perceive")
    graph.add_edge("perceive", "decide")
    graph.add_edge("decide", END)
    return graph


def compile_agent_runtime(
    provider: FakeProvider | None = None, *, model: str = "fake:small"
) -> CompiledStateGraph[AgentGraphState, None, AgentGraphState, AgentGraphState]:
    fake = provider or FakeProvider(script=["acknowledge"])
    return build_agent_graph(fake, model=model).compile(checkpointer=MemorySaver())
