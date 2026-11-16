import os
from pathlib import Path

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

# API keys live in the git-ignored src/agentic_flow/.env file: GROQ_API_KEY=...
load_dotenv(Path(__file__).parents[1] / ".env")

# "<provider>:<model>". Switch provider by setting IDE3_MODEL, with no code change:
#   groq:openai/gpt-oss-120b         needs GROQ_API_KEY    (pip install langchain-groq)
#   google_genai:gemini-2.5-flash    needs GOOGLE_API_KEY  (pip install langchain-google-genai)
#   ollama:llama3.1                  local, no key         (pip install langchain-ollama)
# Groq retired its hosted Llama 3.x models on 2026-08-16 and names gpt-oss-120b as
# the replacement. Hosted model IDs change: check the provider's model list.
MODEL = os.environ.get("IDE3_MODEL", "groq:openai/gpt-oss-120b")


def make_model(
    model: str = MODEL, temperature: float = 0.0, timeout: float = 30, max_retries: int = 6, **kwargs
):
    # configurable_fields makes the client lazy: it is created on the first call,
    # so importing the graphs (tests, drawing) does not need an API key.
    # timeout: a stuck request fails (and is retried) instead of hanging the chat.
    # max_retries: free tiers limit tokens per minute (Groq: 8000, about 3 evaluations);
    # the client waits and retries on a rate-limit reply instead of crashing the chat.
    return init_chat_model(
        model,
        temperature=temperature,
        timeout=timeout,
        max_retries=max_retries,
        configurable_fields=("model", "model_provider"),
        **kwargs,
    )


base_model = make_model()
