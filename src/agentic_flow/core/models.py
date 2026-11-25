"""The shared chat model, configured from the environment or the git-ignored
`.env` at the repository root (variables already set in the shell win).

IDE3_PROVIDER picks the provider: tokenrouter | ollama-cloud | ollama-local.
Without it, the first match wins:
    TOKENROUTER_API_KEY   TokenRouter (OpenAI-compatible), model TOKENROUTER_MODEL
    OLLAMA_API_KEY        Ollama Cloud, model OLLAMA_MODEL
    (neither)             local Ollama, model OLLAMA_LOCAL_MODEL
IDE3_MODEL overrides the model name for whichever provider is used.
"""
import os
from dataclasses import dataclass
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[3] / ".env"
PROVIDERS = ("tokenrouter", "ollama-cloud", "ollama-local")
TIMEOUT_SECONDS = 180


def _load_env_file() -> None:
    if not ENV_FILE.is_file():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


@dataclass(frozen=True)
class ModelConfig:
    provider: str
    model: str
    base_url: str | None  # None: local Ollama on localhost (or $OLLAMA_HOST)
    api_key: str | None


def _model_config() -> ModelConfig:
    env = os.environ.get
    forced = (env("IDE3_PROVIDER") or "").strip().lower()
    if forced and forced not in PROVIDERS:
        raise ValueError(f"IDE3_PROVIDER must be one of {', '.join(PROVIDERS)}; got {forced!r}.")

    if forced == "tokenrouter" or (not forced and env("TOKENROUTER_API_KEY")):
        provider, key = "tokenrouter", env("TOKENROUTER_API_KEY")
        model, url = env("TOKENROUTER_MODEL") or "openai/gpt-5.4-nano", "https://api.tokenrouter.com/v1"
    elif forced == "ollama-cloud" or (not forced and env("OLLAMA_API_KEY")):
        provider, key = "ollama-cloud", env("OLLAMA_API_KEY")
        model, url = env("OLLAMA_MODEL") or "gpt-oss:120b", "https://ollama.com"
    else:
        provider, key = "ollama-local", None
        model, url = env("OLLAMA_LOCAL_MODEL") or "qwen2.5:7b", None

    if provider != "ollama-local" and not key:
        raise ValueError(f"IDE3_PROVIDER={provider} needs its API key in the environment or .env.")
    return ModelConfig(provider, env("IDE3_MODEL") or model, url, key)


# Longest real reply so far is ~400 tokens. The cap stops a model stuck repeating
# itself; NUM_CTX fits the prompt (PRD + instructions) plus that reply.
MAX_OUTPUT_TOKENS = 2048
NUM_CTX = 8192


def _make_model(config: ModelConfig):
    # temperature 0 for repeatable extraction
    if config.provider == "tokenrouter":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=config.model, base_url=config.base_url, api_key=config.api_key,
                          temperature=0.0, max_tokens=MAX_OUTPUT_TOKENS,
                          timeout=TIMEOUT_SECONDS, max_retries=2)

    from langchain_ollama import ChatOllama

    # ChatOllama takes its timeout and auth header through the HTTP client
    client_kwargs: dict = {"timeout": TIMEOUT_SECONDS}
    if config.api_key:
        client_kwargs["headers"] = {"Authorization": f"Bearer {config.api_key}"}
    return ChatOllama(model=config.model, base_url=config.base_url, temperature=0.0,
                      num_predict=MAX_OUTPUT_TOKENS, num_ctx=NUM_CTX,
                      client_kwargs=client_kwargs)


def describe_model() -> str:
    """For banners and logs; never includes the key."""
    c = MODEL_CONFIG
    return f"{c.model} via {c.provider} ({c.base_url or 'localhost'})"


_load_env_file()
MODEL_CONFIG = _model_config()
base_model = _make_model(MODEL_CONFIG)
