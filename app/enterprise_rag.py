"""Governed enterprise retrieval for the SAP Finance assistant."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


# Common words that do not help distinguish finance policies.
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "before",
    "by",
    "can",
    "do",
    "does",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "may",
    "of",
    "on",
    "or",
    "please",
    "should",
    "that",
    "the",
    "this",
    "to",
    "what",
    "when",
    "who",
    "with",
}


# Normalize common word variants to improve keyword matching.
TOKEN_ALIASES = {
    "accounting": "account",
    "adjustments": "adjustment",
    "approvals": "approval",
    "approved": "approve",
    "approver": "approve",
    "approvers": "approve",
    "auditing": "audit",
    "auditors": "auditor",
    "changed": "change",
    "changes": "change",
    "entries": "entry",
    "evidences": "evidence",
    "journals": "journal",
    "payments": "payment",
    "policies": "policy",
    "posted": "post",
    "posting": "post",
    "records": "record",
    "restricted": "restrict",
    "restrictions": "restrict",
    "reviewed": "review",
    "reviewers": "review",
    "reviews": "review",
    "transactions": "transaction",
}


# Phrases associated with attempts to override governance rules.
PROMPT_INJECTION_MARKERS = (
    "ignore all previous",
    "ignore previous instructions",
    "ignore previous rules",
    "disregard all previous",
    "override the rules",
    "bypass access",
    "bypass security",
    "reveal the system prompt",
    "show the hidden instructions",
)


@dataclass(frozen=True)
class RetrievalQuery:
    """A validated enterprise retrieval request."""

    question: str
    user_role: str
    company_code: str
    top_k: int = 5

    def __post_init__(self) -> None:
        """Validate and normalize the request."""

        clean_question = str(self.question).strip()
        clean_role = str(self.user_role).strip().upper()
        clean_company_code = (
            str(self.company_code).strip().upper()
        )

        if not clean_question:
            raise ValueError(
                "The retrieval question cannot be empty."
            )

        if not clean_role:
            raise ValueError(
                "The user role cannot be empty."
            )

        if not clean_company_code:
            raise ValueError(
                "The company code cannot be empty."
            )

        if not isinstance(self.top_k, int):
            raise TypeError(
                "top_k must be an integer."
            )

        if self.top_k < 1 or self.top_k > 20:
            raise ValueError(
                "top_k must be between 1 and 20."
            )

        object.__setattr__(
            self,
            "question",
            clean_question,
        )

        object.__setattr__(
            self,
            "user_role",
            clean_role,
        )

        object.__setattr__(
            self,
            "company_code",
            clean_company_code,
        )


@dataclass(frozen=True)
class RetrievalResult:
    """One authorized enterprise-policy search result."""

    chunk_id: str
    policy_id: str
    citation: str
    title: str
    text: str
    score: float
    user_role: str
    company_code: str

    def to_dict(self) -> dict[str, Any]:
        """Convert the result to a JSON-friendly dictionary."""

        return {
            "chunk_id": self.chunk_id,
            "policy_id": self.policy_id,
            "citation": self.citation,
            "title": self.title,
            "text": self.text,
            "score": self.score,
            "user_role": self.user_role,
            "company_code": self.company_code,
        }


@dataclass(frozen=True)
class RetrievalBatch:
    """Authorized results and privacy-safe audit evidence."""

    results: list[RetrievalResult]
    audit_event: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Convert the batch to a JSON-friendly dictionary."""

        return {
            "results": [
                result.to_dict()
                for result in self.results
            ],
            "audit_event": dict(self.audit_event),
        }


def normalize_token(token: str) -> str:
    """Normalize one token for deterministic retrieval."""

    clean_token = token.lower().strip()

    return TOKEN_ALIASES.get(
        clean_token,
        clean_token,
    )


def tokenize(text: str) -> set[str]:
    """Convert text into normalized retrieval terms."""

    raw_tokens = re.findall(
        r"[A-Za-z0-9_-]+",
        str(text).lower(),
    )

    normalized_tokens = {
        normalize_token(token)
        for token in raw_tokens
        if token not in STOP_WORDS
    }

    return {
        token
        for token in normalized_tokens
        if len(token) > 1
    }


def first_value(
    item: dict[str, Any],
    field_names: tuple[str, ...],
    default: Any = None,
) -> Any:
    """Read the first available field, including metadata fields."""

    metadata = item.get("metadata", {})

    if not isinstance(metadata, dict):
        metadata = {}

    for field_name in field_names:
        if field_name in item:
            value = item[field_name]

            if value not in (None, "", []):
                return value

        if field_name in metadata:
            value = metadata[field_name]

            if value not in (None, "", []):
                return value

    return default


def to_string_list(value: Any) -> list[str]:
    """Convert a scalar or collection into normalized strings."""

    if value is None:
        return []

    if isinstance(value, str):
        # Support comma-separated access-control values.
        raw_values = re.split(
            r"[,;|]",
            value,
        )

    elif isinstance(value, (list, tuple, set)):
        raw_values = list(value)

    else:
        raw_values = [value]

    return [
        str(item).strip().upper()
        for item in raw_values
        if str(item).strip()
    ]


def extract_chunks(
    chunk_catalog: Any,
) -> list[dict[str, Any]]:
    """Extract chunks from common JSON catalog structures."""

    if isinstance(chunk_catalog, list):
        raw_chunks = chunk_catalog

    elif isinstance(chunk_catalog, dict):
        collection_keys = (
            "chunks",
            "documents",
            "policies",
            "records",
            "items",
            "data",
        )

        raw_chunks = None

        for collection_key in collection_keys:
            candidate = chunk_catalog.get(
                collection_key
            )

            if isinstance(candidate, list):
                raw_chunks = candidate
                break

        # Support dictionaries keyed by chunk or policy ID.
        if raw_chunks is None:
            dictionary_values = list(
                chunk_catalog.values()
            )

            if dictionary_values and all(
                isinstance(value, dict)
                for value in dictionary_values
            ):
                raw_chunks = dictionary_values
            else:
                raw_chunks = []

    else:
        raise TypeError(
            "The chunk catalog must be a list or dictionary."
        )

    return [
        dict(chunk)
        for chunk in raw_chunks
        if isinstance(chunk, dict)
    ]


class EnterpriseFinanceRetriever:
    """Retrieve only role-authorized enterprise Finance content."""

    def __init__(
        self,
        chunk_catalog: Any,
    ) -> None:
        """Initialize and normalize the enterprise chunk catalog."""

        self.chunks = extract_chunks(
            chunk_catalog
        )

        if not self.chunks:
            raise ValueError(
                "The enterprise chunk catalog contains no records."
            )


    @staticmethod
    def _question_is_injection(
        question: str,
    ) -> bool:
        """Detect basic attempts to override governance controls."""

        normalized_question = " ".join(
            question.lower().split()
        )

        return any(
            marker in normalized_question
            for marker in PROMPT_INJECTION_MARKERS
        )


    @staticmethod
    def _chunk_id(
        chunk: dict[str, Any],
        position: int,
    ) -> str:
        """Read or generate a stable chunk identifier."""

        value = first_value(
            chunk,
            (
                "chunk_id",
                "id",
                "document_id",
                "record_id",
            ),
            default=f"CHUNK-{position:03d}",
        )

        return str(value)


    @staticmethod
    def _policy_id(
        chunk: dict[str, Any],
        position: int,
    ) -> str:
        """Read or generate a stable policy identifier."""

        value = first_value(
            chunk,
            (
                "policy_id",
                "policy",
                "source_id",
                "document_id",
            ),
            default=f"POLICY-{position:03d}",
        )

        return str(value)


    @staticmethod
    def _title(
        chunk: dict[str, Any],
    ) -> str:
        """Read a policy or chunk title."""

        value = first_value(
            chunk,
            (
                "title",
                "policy_title",
                "name",
                "heading",
            ),
            default="Untitled Finance Policy",
        )

        return str(value)


    @staticmethod
    def _text(
        chunk: dict[str, Any],
    ) -> str:
        """Read the searchable policy text."""

        value = first_value(
            chunk,
            (
                "text",
                "content",
                "chunk_text",
                "policy_text",
                "body",
                "description",
                "summary",
            ),
            default="",
        )

        return str(value)


    @staticmethod
    def _citation(
        chunk: dict[str, Any],
        policy_id: str,
        chunk_id: str,
    ) -> str:
        """Read or generate the source citation."""

        value = first_value(
            chunk,
            (
                "citation",
                "source_citation",
                "reference",
            ),
            default="",
        )

        if value:
            return str(value)

        return f"{policy_id}#{chunk_id}"


    @staticmethod
    def _allowed_roles(
        chunk: dict[str, Any],
    ) -> list[str]:
        """Read the roles permitted to retrieve a chunk."""

        value = first_value(
            chunk,
            (
                "allowed_roles",
                "authorized_roles",
                "permitted_roles",
                "roles",
                "role_access",
            ),
            default=[],
        )

        return to_string_list(value)


    @staticmethod
    def _allowed_company_codes(
        chunk: dict[str, Any],
    ) -> list[str]:
        """Read the company codes permitted to retrieve a chunk."""

        value = first_value(
            chunk,
            (
                "company_codes",
                "allowed_company_codes",
                "authorized_company_codes",
                "company_code",
                "entities",
                "entity_codes",
            ),
            default=[],
        )

        return to_string_list(value)


    @staticmethod
    def _classification(
        chunk: dict[str, Any],
    ) -> str:
        """Read the chunk's information classification."""

        value = first_value(
            chunk,
            (
                "classification",
                "sensitivity",
                "data_classification",
            ),
            default="INTERNAL",
        )

        return str(value).strip().upper()


    @staticmethod
    def _keywords(
        chunk: dict[str, Any],
    ) -> str:
        """Read optional retrieval keywords."""

        value = first_value(
            chunk,
            (
                "keywords",
                "tags",
                "search_terms",
                "topics",
            ),
            default=[],
        )

        if isinstance(value, str):
            return value

        if isinstance(value, (list, tuple, set)):
            return " ".join(
                str(item)
                for item in value
            )

        return str(value)


    def _role_is_authorized(
        self,
        chunk: dict[str, Any],
        user_role: str,
    ) -> bool:
        """Apply fail-closed role authorization."""

        allowed_roles = self._allowed_roles(
            chunk
        )

        if allowed_roles:
            return (
                "*" in allowed_roles
                or "ALL" in allowed_roles
                or user_role in allowed_roles
            )

        # Records with no explicit roles are accessible only when
        # they are marked as public or general.
        classification = self._classification(
            chunk
        )

        return classification in {
            "PUBLIC",
            "GENERAL",
        }


    def _company_is_authorized(
        self,
        chunk: dict[str, Any],
        company_code: str,
    ) -> bool:
        """Apply fail-closed company-code authorization."""

        allowed_company_codes = (
            self._allowed_company_codes(
                chunk
            )
        )

        if allowed_company_codes:
            return (
                "*" in allowed_company_codes
                or "ALL" in allowed_company_codes
                or company_code
                in allowed_company_codes
            )

        # Public and general records may span company codes.
        classification = self._classification(
            chunk
        )

        return classification in {
            "PUBLIC",
            "GENERAL",
        }


    @staticmethod
    def _score_chunk(
        question: str,
        title: str,
        text: str,
        keywords: str,
        policy_id: str,
    ) -> float:
        """Calculate deterministic keyword relevance."""

        question_tokens = tokenize(
            question
        )

        title_tokens = tokenize(
            title
        )

        text_tokens = tokenize(
            text
        )

        keyword_tokens = tokenize(
            keywords
        )

        policy_tokens = tokenize(
            policy_id
        )

        title_overlap = (
            question_tokens
            & title_tokens
        )

        text_overlap = (
            question_tokens
            & text_tokens
        )

        keyword_overlap = (
            question_tokens
            & keyword_tokens
        )

        policy_overlap = (
            question_tokens
            & policy_tokens
        )

        # Titles and configured keywords receive a higher weight.
        score = (
            len(title_overlap) * 3.0
            + len(keyword_overlap) * 2.5
            + len(text_overlap) * 1.0
            + len(policy_overlap) * 0.5
        )

        return round(
            score,
            4,
        )


    def retrieve(
        self,
        query: RetrievalQuery,
    ) -> RetrievalBatch:
        """Return only authorized, relevant Finance policy chunks."""

        if not isinstance(
            query,
            RetrievalQuery,
        ):
            raise TypeError(
                "query must be a RetrievalQuery instance."
            )

        query_hash = hashlib.sha256(
            query.question.encode("utf-8")
        ).hexdigest()[:16]


        # Prompt-injection attempts do not receive retrieved context.
        if self._question_is_injection(
            query.question
        ):
            audit_event = {
                "event_type": "enterprise_retrieval",
                "timestamp_utc": datetime.now(
                    timezone.utc
                ).isoformat(),
                "query_hash": query_hash,
                "user_role": query.user_role,
                "company_code": query.company_code,
                "top_k": query.top_k,
                "candidate_count": len(
                    self.chunks
                ),
                "authorized_count": 0,
                "result_count": 0,
                "returned_policy_ids": [],
                "control_result": (
                    "prompt_injection_blocked"
                ),
            }

            return RetrievalBatch(
                results=[],
                audit_event=audit_event,
            )


        authorized_candidates = []


        for position, chunk in enumerate(
            self.chunks,
            start=1,
        ):
            role_authorized = (
                self._role_is_authorized(
                    chunk,
                    query.user_role,
                )
            )

            company_authorized = (
                self._company_is_authorized(
                    chunk,
                    query.company_code,
                )
            )

            if not (
                role_authorized
                and company_authorized
            ):
                continue


            chunk_id = self._chunk_id(
                chunk,
                position,
            )

            policy_id = self._policy_id(
                chunk,
                position,
            )

            title = self._title(
                chunk
            )

            text = self._text(
                chunk
            )

            keywords = self._keywords(
                chunk
            )

            citation = self._citation(
                chunk,
                policy_id,
                chunk_id,
            )

            score = self._score_chunk(
                question=query.question,
                title=title,
                text=text,
                keywords=keywords,
                policy_id=policy_id,
            )


            # Irrelevant policies are not returned.
            if score <= 0:
                continue


            authorized_candidates.append(
                RetrievalResult(
                    chunk_id=chunk_id,
                    policy_id=policy_id,
                    citation=citation,
                    title=title,
                    text=text,
                    score=score,
                    user_role=query.user_role,
                    company_code=query.company_code,
                )
            )


        # Highest relevance first, followed by stable identifiers.
        authorized_candidates.sort(
            key=lambda result: (
                -result.score,
                result.policy_id,
                result.chunk_id,
            )
        )


        selected_results = (
            authorized_candidates[
                :query.top_k
            ]
        )


        returned_policy_ids = list(
            dict.fromkeys(
                result.policy_id
                for result in selected_results
            )
        )


        audit_event = {
            "event_type": "enterprise_retrieval",
            "timestamp_utc": datetime.now(
                timezone.utc
            ).isoformat(),
            "query_hash": query_hash,
            "user_role": query.user_role,
            "company_code": query.company_code,
            "top_k": query.top_k,
            "candidate_count": len(
                self.chunks
            ),
            "authorized_count": len(
                authorized_candidates
            ),
            "result_count": len(
                selected_results
            ),
            "returned_policy_ids": (
                returned_policy_ids
            ),
            "control_result": (
                "authorized_retrieval_completed"
            ),
        }


        return RetrievalBatch(
            results=selected_results,
            audit_event=audit_event,
        )
