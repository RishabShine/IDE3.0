"""Chat with the whole capture-intent graph. From src/:

    python -m agentic_flow.capture_intent.chat

Paste a PRD; the graph derives the intent from it. Finish the paste with two
empty lines (or END).

    --sample / --file prd.txt   use a sample PRD or a file instead, run once
    --json                      also print the raw captured_intent
    --quiet                     hide each model response
    --out intent.json           save {prd, captured_intent}, the stakeholders step's input
"""
from agentic_flow.capture_intent.chat_utils import chat
from agentic_flow.capture_intent.graph import build_capture_intent

if __name__ == "__main__":
    chat(build_capture_intent, "Capture intent (full graph)",
         "SSON graph -> context graph; fills state['captured_intent']")
