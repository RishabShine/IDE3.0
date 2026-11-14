from langchain_ollama import ChatOllama
from typing import Optional

def make_model(
    model: str,
    temperature: float,
    max_tokens: int,
    timeout: float | None = None,
    max_retries: int = 2,
) -> ChatOllama:
    return ChatOllama(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        max_retries=max_retries,
    )

base_model = make_model(
    model="llama2:7b-chat",
    temperature=0.0,
    max_tokens=1024,
    timeout=30,
    max_retries=2,
)