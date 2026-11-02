"""Role-aware retrieval for the governed Finance assistant."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9]+")


@dataclass(frozen=True)
class RetrievalQuery:
    """Validated enterprise retrieval request."""

    question: str
    user_role: str
    company_code: str
    top_k: int = 3
    minimum_score: float = 0.01

    def __post_init__(self) -> None:
        if not self.question.strip():
            raise ValueError("question must not be empty.")

        if not self.user_role.strip():
            raise ValueError("user_role must not be empty.")

        if not self.company_code.strip():
            raise ValueError("company_code must not be empty.")

        if self.top_k <= 0:
            raise ValueError("top_k must be greater than zero.")

        if not 0.0 <= self.minimum_score <= 1.0:
            raise ValueError(
                "minimum_score must be between 0.0 and 1.0."
            )


@dataclass(frozen=True)
class RetrievalResult:
    """One authorized and ranked policy chunk."""

    chunk_id: str
    policy_id: str
    title: str
    content: str
    score: float
    citation: str
    source_uri: str
    business_domain: str

    def to_prompt_context(self) -> dict[str, Any]:
        """Return only the fields that the model needs."""

        return {
            "policy_id": self.policy_id,
            "chunk_id": self.chunk_id,
            "title": self.title,
            "content": self.content,
            "citation": self.citation,
            "source_uri": self.source_uri,
            "business_domain": self.business_domain,
        }


@dataclass(frozen=True)
class RetrievalBatch:
    """Results and audit evidence for one retrieval request."""

    results: tuple[RetrievalResult, ...]
    audit_event: dict[str, Any]


def tokenize(text: str) -> list[str]:
    """Normalize text into lowercase searchable tokens."""

    return [
        token.lower()
        for token in TOKEN_PATTERN.findall(text)
    ]


def term_frequency(text: str) -> Counter[str]:
    """Create a simple local vector from token counts."""

    return Counter(tokenize(text))


def cosine_similarity(
    left_vector: Counter[str],
    right_vector: Counter[str],
) -> float:
    """Calculate cosine similarity between two term vectors."""

    shared_terms = set(left_vector) & set(right_vector)

    dot_product = sum(
        left_vector[term] * right_vector[term]
        for term in shared_terms
    )

    left_length = math.sqrt(
        sum(value * value for value in left_vector.values())
    )

    right_length = math.sqrt(
        sum(value * value for value in right_vector.values())
    )

    if left_length == 0.0 or right_length == 0.0:
        return 0.0

    return dot_product / (left_length * right_length)


class EnterpriseFinanceRetriever:
    """Filter enterprise access before ranking Finance chunks."""

    def __init__(self, chunks: list[dict[str, Any]]) -> None:
        if not chunks:
            raise ValueError("At least one policy chunk is required.")

        self.chunks = chunks

    @staticmethod
    def _is_authorized(
        chunk: dict[str, Any],
        user_role: str,
        company_code: str,
    ) -> bool:
        """Apply role and company-code authorization."""

        normalized_role = user_role.strip().upper()
        normalized_company = company_code.strip().upper()

        allowed_roles = {
            str(role).strip().upper()
            for role in chunk.get("allowed_roles", [])
        }

        company_codes = {
            str(code).strip().upper()
            for code in chunk.get("company_codes", [])
        }

        role_allowed = (
            "*" in allowed_roles
            or normalized_role in allowed_roles
        )

        company_allowed = (
            "*" in company_codes
            or normalized_company in company_codes
        )

        return role_allowed and company_allowed

    @staticmethod
    def _searchable_text(chunk: dict[str, Any]) -> str:
        """Combine approved fields used for ranking."""

        return " ".join(
            [
                str(chunk.get("policy_id", "")),
                str(chunk.get("title", "")),
                str(chunk.get("content", "")),
                str(chunk.get("business_domain", "")),
            ]
        )

    def retrieve(self, query: RetrievalQuery) -> RetrievalBatch:
        """Filter first and rank only authorized policy chunks."""

        authorized_chunks = [
            chunk
            for chunk in self.chunks
            if self._is_authorized(
                chunk,
                query.user_role,
                query.company_code,
            )
        ]

        query_vector = term_frequency(query.question)
        ranked_results: list[RetrievalResult] = []

        for chunk in authorized_chunks:
            chunk_vector = term_frequency(
                self._searchable_text(chunk)
            )

            score = cosine_similarity(
                query_vector,
                chunk_vector,
            )

            if score < query.minimum_score:
                continue

            policy_id = str(chunk["policy_id"])
            chunk_id = str(chunk["chunk_id"])

            ranked_results.append(
                RetrievalResult(
                    chunk_id=chunk_id,
                    policy_id=policy_id,
                    title=str(chunk["title"]),
                    content=str(chunk["content"]),
                    score=round(score, 6),
                    citation=f"{policy_id}#{chunk_id}",
                    source_uri=str(chunk["source_uri"]),
                    business_domain=str(
                        chunk["business_domain"]
                    ),
                )
            )

        ranked_results.sort(
            key=lambda result: (
                -result.score,
                result.policy_id,
                result.chunk_id,
            )
        )

        selected_results = tuple(
            ranked_results[:query.top_k]
        )

        # Hash the question instead of storing its full text.
        query_hash = hashlib.sha256(
            query.question.encode("utf-8")
        ).hexdigest()[:16]

        audit_event = {
            "event_type": "enterprise_policy_retrieval",
            "timestamp_utc": datetime.now(
                timezone.utc
            ).isoformat(),
            "query_hash": query_hash,
            "user_role": query.user_role.upper(),
            "company_code": query.company_code,
            "total_chunks": len(self.chunks),
            "authorized_chunks": len(authorized_chunks),
            "ranked_chunks": len(ranked_results),
            "returned_chunks": len(selected_results),
            "returned_citations": [
                result.citation
                for result in selected_results
            ],
        }

        return RetrievalBatch(
            results=selected_results,
            audit_event=audit_event,
        )
