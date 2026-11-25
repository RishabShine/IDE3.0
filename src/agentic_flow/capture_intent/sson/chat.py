"""Try the SSON step alone. From src/:

    python -m agentic_flow.capture_intent.sson.chat            paste PRDs
    python -m agentic_flow.capture_intent.sson.chat --sample   one run on a sample PRD
"""
from agentic_flow.capture_intent.chat_utils import chat
from agentic_flow.capture_intent.sson.graph import build_capture_sson

if __name__ == "__main__":
    chat(build_capture_sson, "Capture intent: SSON (G.1)",
         "extract_sson -> evaluate_sson")
