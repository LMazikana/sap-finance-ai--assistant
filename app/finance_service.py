# DAY 6 — ACTIVITY 3: CREATE THE FINANCE SERVICE LAYER
#
# Purpose:
# Connect the validated API request to the existing retriever.
#
# The service returns an evidence-grounded response or refuses
# to answer when no approved source is found.

from uuid import uuid4

from app.retriever import load_policies, retrieve_policies
from app.schemas import (
    FinanceAnswerResponse,
    FinanceQuestionRequest,
    SourceCitation,
)


def answer_finance_question(
    request: FinanceQuestionRequest,
    policy_file: str = "data/finance_policies.json",
) -> FinanceAnswerResponse:
    """
    Answer a validated finance question using approved evidence.
    """

    # Assign a unique identifier for future audit logging.
    request_id = str(uuid4())

    # Load the approved synthetic policy collection.
    policies = load_policies(policy_file)

    # Retrieve the policies most relevant to the question.
    retrieved_policies = retrieve_policies(
        query=request.question,
        policies=policies,
        top_k=request.top_k,
    )

    # Fail closed when no approved supporting evidence is found.
    if not retrieved_policies:
        return FinanceAnswerResponse(
            request_id=request_id,
            status="refused",
            answer=(
                "I cannot answer this question because no approved "
                "finance-policy evidence was retrieved."
            ),
            user_role=request.user_role,
            decision_reason="No approved supporting evidence was found.",
            citations=[],
        )

    # Select the highest-scoring policy as the primary evidence.
    best_policy = retrieved_policies[0]

    # Convert all retrieved policies into structured citations.
    citations = [
        SourceCitation(
            policy_id=policy["policy_id"],
            title=policy["title"],
            citation=policy["citation"],
            retrieval_score=policy["retrieval_score"],
        )
        for policy in retrieved_policies
    ]

    # Return the policy text directly.
    # No LLM is used, so the service cannot invent additional content.
    return FinanceAnswerResponse(
        request_id=request_id,
        status="grounded",
        answer=(
            f"Based on {best_policy['title']}: "
            f"{best_policy['text']}"
        ),
        user_role=request.user_role,
        decision_reason="Approved policy evidence was retrieved.",
        citations=citations,
    )


def handle_finance_api(
    payload: dict,
    policy_file: str = "data/finance_policies.json",
) -> dict:
    """
    Simulate an API endpoint using a JSON-style Python dictionary.

    A future FastAPI, Databricks Model Serving or SAP BTP endpoint
    can call this same service function.
    """

    # Validate the incoming dictionary against the request schema.
    validated_request = FinanceQuestionRequest.model_validate(payload)

    # Process the validated request.
    response = answer_finance_question(
        request=validated_request,
        policy_file=policy_file,
    )

    # Convert the response into a JSON-compatible dictionary.
    return response.model_dump(mode="json")
