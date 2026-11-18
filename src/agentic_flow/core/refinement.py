"""Small shared helpers for review limits and refinement context."""
MAX_REFINEMENT_ATTEMPTS = 2


def checks_pass(metadata, evaluation_key):
    return all(item["overall_verdict"] == "met"
               for item in metadata["evaluation"][evaluation_key])


def asked_about(metadata, evaluation_key, id_field):
    """Derive targets from questions actually shown; do not store another list."""
    if not metadata.get("evaluation") or metadata.get("model_error"):
        return []
    current_ids = {draft[id_field] for draft in metadata["drafts"]}
    shown = metadata["last_prompt_to_user"]
    return [
        item[id_field]
        for item in metadata["evaluation"][evaluation_key]
        if item[id_field] in current_ids and any(
            key.endswith("_feedback") and text and text in shown
            and item.get(key.removesuffix("_feedback") + "_verdict") != "met"
            for key, text in item.items()
        )
    ]


def review_note(metadata, evaluation_key, id_field):
    if checks_pass(metadata, evaluation_key):
        return "All current drafts meet the evaluation checks."
    issues = []
    for item in metadata["evaluation"][evaluation_key]:
        if item["overall_verdict"] == "met":
            continue
        feedback = dict.fromkeys(
            text for key, text in item.items()
            if key.endswith("_feedback") and text
            and item.get(key.removesuffix("_feedback") + "_verdict") != "met"
        )
        issues.append(f"- {item[id_field]}: " + (
            " ".join(feedback) or "Some evaluation checks are still incomplete."
        ))
    return (
        f"After {metadata.get('refinement_attempts', 0)} completed evaluations, "
        "some checks are still unresolved. You can APPROVE this list as-is or "
        "describe changes to keep refining it. Approval does not mark these "
        "checks as met.\n\nOutstanding feedback:\n" + "\n".join(issues)
    )
