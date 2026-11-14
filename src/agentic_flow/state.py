from typing import Literal, TypedDict

Verdict = Literal["met", "partially_met", "not_met"]


class IntentCapture(TypedDict):
    single_statement_intent: str
    evaluation_of_statement: Verdict
    evaluation_of_statement_feedback: str
    attempt_number: int


# the total agent memory state, which is a dictionary of all the states of the agent
class AgentState(TypedDict):

    project_context: str

    # Capture Intent State
    intent_metadata: IntentCapture
