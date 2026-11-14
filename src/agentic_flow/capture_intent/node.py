from langchain_core.messages import HumanMessage, SystemMessage

from agentic_flow.capture_intent.prompts import (
    SINGLE_STATEMENT_OF_NEED_STARTER_PROMPT,
    SINGLE_STATEMENT_OF_NEED_EVALUATION_PROMPT,
)
from agentic_flow.capture_intent.schema import IntentSSONEvaluation
from agentic_flow.core.models import base_model
from agentic_flow.core.shared_nodes import get_user_input
from agentic_flow.state import AgentState


def capture_intent(state: AgentState) -> AgentState:
    """
    Ask the user for their Single Statement of Need. Shows the starter prompt
    (definition + examples) on the first attempt, and the previous attempt's
    evaluation feedback on every retry. Writes the reply into intent_metadata.
    """

    intent_metadata = state.get("intent_metadata", {})
    attempt_number = intent_metadata.get("attempt_number", 0)

    prompt = (
        SINGLE_STATEMENT_OF_NEED_STARTER_PROMPT
        if attempt_number == 0
        else intent_metadata["evaluation_of_statement_feedback"]
    )

    statement = get_user_input(prompt=prompt)

    return {
        "intent_metadata": {
            **intent_metadata,
            "single_statement_intent": statement,
            "attempt_number": attempt_number,
        }
    }


def evaluate_SSON(state: AgentState) -> AgentState:
    """
    Evaluate the user's Single Statement of Need (SSON) against the criteria
    provided in the prompt. If the SSON does not meet the criteria, the graph
    loops back to capture_intent, which re-asks using this feedback.
    """
    
    attempt_number = state["intent_metadata"]["attempt_number"] + 1
    statement = state["intent_metadata"]["single_statement_intent"]

    model = base_model.with_structured_output(IntentSSONEvaluation)
    response = model.invoke(
        [
            SystemMessage(
                content=SINGLE_STATEMENT_OF_NEED_EVALUATION_PROMPT.format(
                    project_context=state.get("project_context", ""),
                    attempt_number=attempt_number,
                )
            ),
            HumanMessage(content=f"<statement>{statement}</statement>"),
        ]
    )

    return {
        "intent_metadata": {
            "single_statement_intent": statement,
            "evaluation_of_statement": response.evaluation_of_statement,
            "evaluation_of_statement_feedback": response.evaluation_of_statement_feedback,
            "attempt_number": attempt_number,
        },
    }
