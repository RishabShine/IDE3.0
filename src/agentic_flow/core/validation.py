"""Validate model output before a node changes graph state."""
import re

from httpx import HTTPError
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage
from ollama import ResponseError
from pydantic import BaseModel, ConfigDict, ValidationError


class StructuredRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelResponseError(ValueError):
    """A model call could not produce a usable response."""


def invoke_checked(model, schema, messages, check):
    """Allow one correction for parsing/validation errors; retain no chat history."""
    for attempt in range(2):
        try:
            result = schema.model_validate(model.invoke(messages))
            check(result)
            return result
        except (HTTPError, ResponseError, ConnectionError, TimeoutError) as error:
            raise ModelResponseError("The model service could not complete the request.") from error
        except (ValidationError, OutputParserException, ValueError) as error:
            if attempt:
                raise ModelResponseError(str(error)) from error
            task_rules = (
                "Existing IDs must match current records exactly; new records use JSON null. "
                "Do not add an operation to compensate for another invalid operation. "
                "If a requested target is ambiguous, ask in clarification_feedback "
                "instead of guessing operations."
                if "updates" in schema.model_fields else
                "Return exactly one evaluation per current ID, including unchanged records. "
                "ID gaps are valid. Exclude removed records and never return edits or "
                "response-processing fields. Put uncertainty in the relevant feedback field."
            )
            messages = [*messages[:-1], HumanMessage(content=(
                messages[-1].content + "\n\nThe previous output was invalid: " + str(error)
                + "\nReturn a corrected " + schema.__name__ + ". Follow the original user "
                "reply and current records, not the invalid output. " + task_rules
                + " Return only the supplied schema."
            ))]


def _name(value):
    # Involvement is a separate field, so a suffix cannot distinguish groups.
    value = re.sub(r"\s*\((?:in)?direct\)\s*$", "", value, flags=re.IGNORECASE)
    return " ".join(value.split()).casefold()


def check_operations(result, drafts, id_field, next_number):
    removed = getattr(result, "removed_" + id_field + "s")
    # Before any draft exists, every supplied record is a new proposal.
    if not drafts and next_number == 1 and not removed:
        for update in result.updates:
            setattr(update, id_field, None)
    updated = [getattr(u, id_field) for u in result.updates if getattr(u, id_field) is not None]
    if len(removed) != len(set(removed)) or len(updated) != len(set(updated)):
        raise ValueError("Each draft may be updated or removed at most once per response.")
    unknown = set(removed + updated) - set(drafts)
    conflicting = set(removed) & set(updated)
    if unknown or conflicting:
        raise ValueError(f"Unknown IDs: {sorted(unknown)}; conflicting IDs: {sorted(conflicting)}. "
                         f"Valid IDs: {list(drafts)}. Do not update and remove the same draft.")

    def identity(record):
        name = _name(record["name"])
        return (name, record.get("stakeholder_id")) if id_field == "persona_id" else name

    proposed = {key: dict(value) for key, value in drafts.items() if key not in removed}
    deleted_names = {identity(drafts[key]) for key in removed if _name(drafts[key]["name"])}
    for index, update in enumerate(result.updates):
        record = update.model_dump()
        draft_id = getattr(update, id_field)
        if id_field == "stakeholder_id" and not _name(record["name"]):
            raise ValueError("A stakeholder draft must have a name.")
        if draft_id is None and _name(record["name"]) and identity(record) in deleted_names:
            raise ValueError("Do not remove a group and recreate it as a new draft in the same reply.")
        proposed[draft_id if draft_id is not None else ("new", index)] = record
    seen = set()
    for record in proposed.values():
        if not _name(record["name"]):  # Incomplete personas can still be refined.
            continue
        key = identity(record)
        if key in seen:
            raise ValueError("Duplicate draft names: edit the existing record instead of adding it again, "
                             "or distinguish the names if they represent different profiles/groups.")
        seen.add(key)


def check_coverage(records, drafts, id_field):
    ids = [getattr(record, id_field) for record in records]
    missing = sorted(set(drafts) - set(ids))
    unexpected = sorted(set(ids) - set(drafts))
    repeated = sorted({key for key in ids if ids.count(key) > 1})
    if missing or unexpected or repeated:
        raise ValueError("Evaluate each current draft exactly once. "
                         f"Required IDs: {list(drafts)}; missing: {missing}; "
                         f"unexpected: {unexpected}; repeated: {repeated}.")


def failed_metadata(metadata, stage, error, finalized_key):
    """Keep records and the last evaluation for context, but block approval."""
    return {
        **metadata,
        "model_error": {"stage": stage, "detail": str(error)},
        "evaluated_draft_version": None,
        "user_confirmed": False,
        "approved_version": None,
        finalized_key: [],
    }
