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
