"""LangGraph review agent graph: intent -> router -> specialists (parallel) -> gate -> arbitration."""
from typing import Literal

from langgraph.graph import END, START, StateGraph

from app.agent.nodes.arbitration import arbitration_node
from app.agent.nodes.gate import gate_node
from app.agent.nodes.intent import intent_node
from app.agent.nodes.router import router_node
from app.agent.nodes.specialist import specialist_node
from app.agent.state import ReviewState
from app.rag.service import RAGService

COMPILED_GRAPH = None


def build_graph(rag: RAGService):
    """组装状态机。specialist 依赖 rag 服务，用闭包注入。"""
    graph = StateGraph(ReviewState)

    async def specialists(state: ReviewState) -> dict:
        return await specialist_node(state, rag)

    graph.add_node("intent", intent_node)
    graph.add_node("router", router_node)
    graph.add_node("specialists", specialists)
    graph.add_node("gate", gate_node)
    graph.add_node("arbitration", arbitration_node)

    graph.add_edge(START, "intent")

    def route_by_intent(state: ReviewState) -> Literal["router", "arbitration"]:
        # 非 review 意图（异常路径）直接产出空结果
        if state.get("intent") != "review":
            return "arbitration"
        return "router"

    graph.add_conditional_edges("intent", route_by_intent, {"router": "router", "arbitration": "arbitration"})
    graph.add_edge("router", "specialists")
    graph.add_edge("specialists", "gate")
    graph.add_edge("gate", "arbitration")
    graph.add_edge("arbitration", END)

    return graph.compile()


def get_graph(rag: RAGService):
    global COMPILED_GRAPH
    if COMPILED_GRAPH is None:
        COMPILED_GRAPH = build_graph(rag)
    return COMPILED_GRAPH
