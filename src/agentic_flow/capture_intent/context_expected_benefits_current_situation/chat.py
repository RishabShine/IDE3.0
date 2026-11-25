"""Try the current situation, benefits and environment steps alone. From src/:

    python -m agentic_flow.capture_intent.context_expected_benefits_current_situation.chat
    python -m agentic_flow.capture_intent.context_expected_benefits_current_situation.chat --sample

Run alone, these steps have no SSON to judge relevance against ("(none)").
Use agentic_flow.capture_intent.chat to run them after the SSON step.
"""
from agentic_flow.capture_intent.chat_utils import chat
from agentic_flow.capture_intent.context_expected_benefits_current_situation.graph import (
    build_capture_context,
)

if __name__ == "__main__":
    chat(build_capture_context, "Capture intent: G.2, G.3, E.5, E.6",
         "extract_current_situation -> extract_expected_benefits -> extract_environment")
