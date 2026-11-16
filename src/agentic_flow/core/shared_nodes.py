from langgraph.config import get_stream_writer
from langgraph.types import interrupt


def get_user_input(prompt: str) -> str:
    """
    Shared building block for any node that needs to pause and collect a message
    from the user. Callers decide what `prompt` to show (a starter question,
    feedback from a previous attempt, etc.) and which state key the reply
    belongs under; this only handles the pause/resume via interrupt() and hands
    back whatever the user typed.
    """
    return interrupt({"prompt_to_user": prompt})


def get_user_choice(prompt: str, options: list[str]) -> str:
    """
    Pause until the user picks one of `options`. Any other reply re-asks with the
    options only. The options are in the payload so a UI can render buttons.
    """
    reply = interrupt({"prompt_to_user": prompt, "options": options})
    while (choice := reply.strip().strip(".!").casefold()) not in options:
        reply = interrupt({
            "prompt_to_user": f"Please reply with one of: {', '.join(options)}.",
            "options": options,
        })
    return choice


def tell_user(message: str) -> None:
    """
    Show the user a message without waiting for a reply. It is sent on LangGraph's
    "custom" stream, so the caller must stream with stream_mode="custom" to see it.
    """
    get_stream_writer()({"message_to_user": message})
