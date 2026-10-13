# DAY 6 — ACTIVITY 2: DEFINE THE API DATA CONTRACT
#
# Purpose:
# Define and validate the information accepted and returned
# by the governed SAP Finance assistant.

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# Only these business roles are currently recognized.
UserRole = Literal[
    "finance_analyst",
    "finance_manager",
    "controller",
    "finance_director",
]


class FinanceQuestionRequest(BaseModel):
    """
    Validated request accepted by the finance assistant.
    """

    # Reject unexpected fields instead of silently ignoring them.
    model_config = ConfigDict(extra="forbid")

    # Require a meaningful question of a controlled size.
    question: str = Field(
        min_length=5,
        max_length=500,
        description="SAP Finance question submitted by the user.",
    )

    # Restrict the role to the approved role list.
    user_role: UserRole

    # Prevent callers from requesting an excessive number of sources.
    top_k: int = Field(default=2, ge=1, le=3)

    @field_validator("question")
    @classmethod
    def clean_and_validate_question(cls, value: str) -> str:
        """
        Remove unnecessary spaces and reject text without letters.
        """

        cleaned_value = " ".join(value.split())

        if not any(character.isalpha() for character in cleaned_value):
            raise ValueError(
                "The question must contain meaningful text."
            )

        return cleaned_value


class SourceCitation(BaseModel):
    """
    Structured citation for one retrieved finance policy.
    """

    policy_id: str
    title: str
    citation: str
    retrieval_score: int


class FinanceAnswerResponse(BaseModel):
    """
    Consistent response returned by the finance service.
    """

    request_id: str
    status: Literal["grounded", "refused"]
    answer: str
    user_role: UserRole
    decision_reason: str

    # Today's application does not call an LLM.
    # The answer comes directly from retrieved policy evidence.
    generation_method: Literal["retrieval_only"] = "retrieval_only"

    citations: list[SourceCitation]
