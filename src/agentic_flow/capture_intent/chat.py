"""Chat with the whole capture-intent graph. From src/:

    python -m agentic_flow.capture_intent.chat

The graph starts with the PRD intake step, waits for you to paste a PRD, then
derives the intent from it. Finish the paste with two empty lines (or END).

    --sample / --file prd.txt   answer the PRD question automatically, run once
    --json                      also print the raw captured_intent
    --quiet                     hide each model response
    --out intent.json           save {prd, captured_intent}, the stakeholders step's input
"""
from langgraph.graph import END, START, StateGraph

from agentic_flow.capture_intent.chat_utils import chat
from agentic_flow.capture_intent.graph import build_capture_intent
from agentic_flow.prd_intake.graph import build_prd_intake
from agentic_flow.state import AgentState


def build_chat_graph(checkpointer=None):
    """PRD intake (asks for the PRD), then capture intent, as in the IDE3.0 pipeline."""
    builder = StateGraph(AgentState)
    builder.add_node("prd_intake_graph", build_prd_intake())
    builder.add_node("capture_intent_graph", build_capture_intent())
    builder.add_edge(START, "prd_intake_graph")
    builder.add_edge("prd_intake_graph", "capture_intent_graph")
    builder.add_edge("capture_intent_graph", END)
    return builder.compile(checkpointer=checkpointer)


if __name__ == "__main__":
    chat(build_chat_graph, "Capture intent (full graph)",
         "PRD intake -> SSON graph -> context graph; fills state['captured_intent']",
         asks_for_prd=True)
