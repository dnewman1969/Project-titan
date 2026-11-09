"""Director LangGraph stub (M6.T4)."""

from __future__ import annotations

from typing import TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph


class DirectorState(TypedDict):
    tick: int
    note: str


def _tick(state: DirectorState) -> DirectorState:
    return {"tick": state.get("tick", 0) + 1, "note": "director_tick"}


def build_director_graph() -> StateGraph:
    graph = StateGraph(DirectorState)
    graph.add_node("tick", _tick)
    graph.add_edge(START, "tick")
    graph.add_edge("tick", END)
    return graph


def compile_director_graph():
    return build_director_graph().compile(checkpointer=MemorySaver())
