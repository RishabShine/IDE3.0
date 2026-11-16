"""
Chat with the flow in a terminal. From src/:
    python -m agentic_flow                  the whole flow
    python -m agentic_flow capture_intent   SSON, current situation, expected benefits only
"""

import json
import sys

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agentic_flow.capture_intent.graph import build_capture_intent
from agentic_flow.graph import requirement_engineer

capture_only = "capture_intent" in sys.argv
graph = build_capture_intent(InMemorySaver()) if capture_only else requirement_engineer
config = {"configurable": {"thread_id": "cli"}}
payload = {"project_context": ""}

while True:
    # Messages sent with tell_user() arrive on the "custom" stream.
    for _, chunk in graph.stream(payload, config, stream_mode="custom", subgraphs=True):
        print(f"\n{chunk['message_to_user']}")

    state = graph.get_state(config)
    if not state.interrupts:
        break
    payload = Command(resume=input(f"\n{state.interrupts[0].value['prompt_to_user']}\n\n> "))

if capture_only:
    print("\nCaptured intent (AgentState['captured_intent']):")
    print(json.dumps(state.values["captured_intent"], indent=2))
