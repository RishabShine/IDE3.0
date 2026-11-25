"""Helpers shared by the capture-intent steps.

Every step reads the PRD, adds its fields to state["captured_intent"], and
keeps whatever earlier steps stored there. The model only extracts; IDs,
traceability checks and red flags are decided here, in code.
"""
import json
import re
from typing import Any

from agentic_flow.state import RED_FLAG, AgentState, CapturedIntent, SourcedItem


def require_prd(state: AgentState) -> str:
    prd = state.get("prd", "")
    if not isinstance(prd, str) or not prd.strip():
        raise ValueError("A non-empty PRD is required for intent capture.")
    return prd


def intent(state: AgentState) -> CapturedIntent:
    return dict(state.get("captured_intent") or {})


def to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _norm(text: str | None) -> str:
    text = (text or "").replace("’", "'").replace("“", '"').replace("”", '"')
    text = " ".join(text.casefold().split())
    return text.strip(" .,;:\"'")


def traced(quote: str | None, prd: str) -> bool:
    """True when the quote appears in the PRD, ignoring case, spacing and end punctuation.

    A quote that joins PRD sentences which are not next to each other also counts,
    as long as every one of its sentences is in the PRD.
    """
    text = _norm(prd)
    sentences = [_norm(s) for s in re.split(r"(?<=[.!?])\s+", quote or "")]
    sentences = [s for s in sentences if s]
    return bool(sentences) and (_norm(quote) in text or all(s in text for s in sentences))


def _stems(text: str) -> set[str]:
    """Content words, cut to 4 letters so "rooms"/"room" and "booked"/"book" match."""
    words = re.findall(r"[a-z0-9%]+", _norm(text))
    return {w[:4] for w in words if len(w) >= 4 or any(c.isdigit() for c in w)}


def supports(source: str, description: str, threshold: float = 0.5) -> bool:
    """True when at least half the description's content words appear in its source.

    Catches a real PRD quote attached to the wrong item, e.g. a targets sentence
    quoted for "volunteer shifts move to batch packing".
    """
    wanted = _stems(description)
    if not wanted:
        return True
    return len(wanted & _stems(source)) / len(wanted) >= threshold


def checked_source(source: str | None, description: str, prd: str) -> str | None:
    """The PRD quote backing an item, or None when nothing in the PRD backs it.

    The model's quote is used when it is in the PRD and supports the description.
    Otherwise, a description copied word for word from the PRD is its own quote
    (the model often attaches a neighbouring sentence to a correct item).
    """
    if source and traced(source, prd) and supports(source, description):
        return source
    description = unflag(description)
    if len(description.split()) >= 4 and traced(description, prd):
        return description
    return None


def same_point(a: str, b: str, threshold: float = 0.7) -> bool:
    """True when two descriptions share most content words, in both directions."""
    return supports(a, b, threshold) and supports(b, a, threshold)


# Wording that says something will not be done: "outside the scope", "will not
# address", "not part of this project", "excluded", ...
_EXCLUSION_CUE = re.compile(
    r"out of scope|outside (of )?the scope|beyond the scope|not (be )?part of|excluded|"
    r"\b(will not|won't|does not|doesn't|do not|cannot|not)\b.{0,30}"
    r"\b(address|cover|include|solve|fix|handle|tackle)",
    re.IGNORECASE,
)


def states_exclusion(quote: str) -> bool:
    return bool(_EXCLUSION_CUE.search(quote or ""))


def flag(text: str) -> str:
    """Mark text the PRD does not state but we derived anyway."""
    text = text.strip()
    if not text or text.startswith(RED_FLAG):
        return text
    return f"{RED_FLAG} {text}"


def unflag(text: str | None) -> str:
    return re.sub(rf"^{RED_FLAG}\s*", "", (text or "").strip())


def sourced_items(extracted, prefix: str, prd: str) -> list[SourcedItem]:
    """Number items Prefix-1..n. An item whose quote is not in the PRD, or does not
    support it, is kept but flagged."""
    items = []
    for item in extracted:
        description = " ".join(item.description.split())
        if not description:
            continue
        source = checked_source(item.source, description, prd)
        items.append({
            "id": f"{prefix}-{len(items) + 1}",
            "description": description if source else flag(description),
            "source": source,
        })
    return items
