"""LangGraph orchestration spine for the five deterministic ShopSage tools."""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class DecisionState(TypedDict):
    completed_nodes: list[str]


def build_decision_graph():
    """Build the auditable tool order; tool implementations are persisted by agent.py."""
    workflow = StateGraph(DecisionState)

    def mark(name: str):
        def node(state: DecisionState):
            return {"completed_nodes": [*state.get("completed_nodes", []), name]}
        return node

    nodes = ["intent_and_constraints", "knowledge_retriever", "catalog_filter", "profile_analyzer", "recommendation_ranker", "citation_validator"]
    for node_name in nodes:
        workflow.add_node(node_name, mark(node_name))
    workflow.add_edge(START, nodes[0])
    for current, following in zip(nodes, nodes[1:]):
        workflow.add_edge(current, following)
    workflow.add_edge(nodes[-1], END)
    return workflow.compile()


decision_graph = build_decision_graph()
