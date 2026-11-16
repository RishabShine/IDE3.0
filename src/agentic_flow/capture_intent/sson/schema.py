from pydantic import BaseModel
from typing import Literal

Verdict = Literal["met", "partially_met", "not_met"]

class IntentSSONEvaluation(BaseModel):
    evaluation_of_statement: Verdict 
    evaluation_of_statement_feedback: str 


