"""Access-aware context construction with citation lineage."""

from __future__ import annotations

import hashlib
import json
import re

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be",
    "before", "by", "do", "does", "for", "from",
    "how", "in", "is", "it", "of", "on", "or",
    "please", "should", "that", "the", "this",
    "to", "what", "when", "who", "with",
}


TOKEN_ALIASES = {
    "approvals": "approval",
    "approved": "approval",
    "approver": "approval",
    "entries": "entry",
    "journals": "journal",
    "payments": "payment",
    "posted": "posting",
    "records": "record",
    "requirements": "requirement",
    "retained": "retention",
}


DEFAULT_INJECTION_MARKERS = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "disregard previous instructions",
    "override authorization",
    "bypass access",
    "bypass security",
    "reveal restricted",
    "reveal the system prompt",
    "show hidden instructions",
)


def _utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


def _normalized_tokens(value: str) -> set[str]:
    words = re.findall(
        r"[a-z0-9]+",
        str(value).lower(),
    )

    return {
        TOKEN_ALIASES.get(word, word)
        for word in words
        if word not in STOP_WORDS
        and len(word) > 1
    }


def _contains_injection(
    value: str,
    markers: Iterable[str],
) -> bool:
    normalized = " ".join(
        str(value).lower().split()
    )

    return any(
        marker in normalized
        for marker in markers
    )


def _token_estimate(value: str) -> int:
    return max(
        1,
        len(
            re.findall(
                r"\S+",
                str(value),
            )
        ),
    )


@dataclass(frozen=True)
class GovernedContextRequest:
    question: str
    user_role: str
    company_code: str
    top_k: int = 3
    token_budget: int = 400

    def __post_init__(self) -> None:
        clean_question = str(
            self.question
        ).strip()

        clean_role = str(
            self.user_role
        ).strip().upper()

        clean_company = str(
            self.company_code
        ).strip().upper()

        if not clean_question:
            raise ValueError(
                "question cannot be empty"
            )

        if not clean_role:
            raise ValueError(
                "user_role cannot be empty"
            )

        if not clean_company:
            raise ValueError(
                "company_code cannot be empty"
            )

        if not isinstance(self.top_k, int):
            raise TypeError(
                "top_k must be an integer"
            )

        if not 1 <= self.top_k <= 10:
            raise ValueError(
                "top_k must be between 1 and 10"
            )

        if not isinstance(
            self.token_budget,
            int,
        ):
            raise TypeError(
                "token_budget must be an integer"
            )

        if not 25 <= self.token_budget <= 4000:
            raise ValueError(
                "token_budget must be between 25 and 4000"
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
            clean_company,
        )


class GovernedContextBuilder:
    def __init__(
        self,
        allowed_classifications=(
            "PUBLIC",
            "INTERNAL",
        ),
        injection_markers=(
            DEFAULT_INJECTION_MARKERS
        ),
    ) -> None:
        self.allowed_classifications = {
            str(item).upper()
            for item in allowed_classifications
        }

        self.injection_markers = tuple(
            str(item).lower()
            for item in injection_markers
        )


    def build(
        self,
        request: GovernedContextRequest,
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if _contains_injection(
            request.question,
            self.injection_markers,
        ):
            return self._blocked_package(
                request=request,
                reason="prompt_injection_in_question",
            )

        query_tokens = _normalized_tokens(
            request.question
        )

        eligible_candidates = []
        rejected_candidates = []
        seen_chunk_ids = set()

        for original_candidate in candidates:
            candidate = dict(
                original_candidate
            )

            chunk_id = str(
                candidate.get(
                    "chunk_id",
                    "",
                )
            ).strip()

            rejection_reasons = []

            if not chunk_id:
                rejection_reasons.append(
                    "missing_chunk_id"
                )

            if chunk_id in seen_chunk_ids:
                rejection_reasons.append(
                    "duplicate_chunk_id"
                )

            seen_chunk_ids.add(chunk_id)

            status = str(
                candidate.get(
                    "status",
                    "",
                )
            ).upper()

            if status != "APPROVED":
                rejection_reasons.append(
                    "content_not_approved"
                )

            allowed_roles = {
                str(role).upper()
                for role in candidate.get(
                    "allowed_roles",
                    [],
                )
            }

            if (
                request.user_role
                not in allowed_roles
                and "*"
                not in allowed_roles
            ):
                rejection_reasons.append(
                    "role_not_authorized"
                )

            company_codes = {
                str(code).upper()
                for code in candidate.get(
                    "company_codes",
                    [],
                )
            }

            if (
                request.company_code
                not in company_codes
                and "*"
                not in company_codes
            ):
                rejection_reasons.append(
                    "company_code_not_authorized"
                )

            classification = str(
                candidate.get(
                    "classification",
                    "",
                )
            ).upper()

            if (
                classification
                not in self.allowed_classifications
            ):
                rejection_reasons.append(
                    "classification_not_allowed"
                )

            candidate_text = " ".join(
                [
                    str(
                        candidate.get(
                            "title",
                            "",
                        )
                    ),
                    str(
                        candidate.get(
                            "content",
                            "",
                        )
                    ),
                    " ".join(
                        str(tag)
                        for tag in candidate.get(
                            "tags",
                            [],
                        )
                    ),
                ]
            )

            if _contains_injection(
                candidate_text,
                self.injection_markers,
            ):
                rejection_reasons.append(
                    "prompt_injection_in_content"
                )

            candidate_tokens = (
                _normalized_tokens(
                    candidate_text
                )
            )

            overlap = (
                query_tokens
                & candidate_tokens
            )

            relevance_score = (
                len(overlap)
                / max(
                    len(query_tokens),
                    1,
                )
            )

            if relevance_score <= 0:
                rejection_reasons.append(
                    "no_relevance"
                )

            if rejection_reasons:
                rejected_candidates.append(
                    {
                        "chunk_id": (
                            chunk_id
                            or "<missing>"
                        ),
                        "reasons": sorted(
                            set(
                                rejection_reasons
                            )
                        ),
                    }
                )

                continue

            candidate[
                "_relevance_score"
            ] = round(
                relevance_score,
                6,
            )

            eligible_candidates.append(
                candidate
            )

        eligible_candidates.sort(
            key=lambda item: (
                -item[
                    "_relevance_score"
                ],
                item["chunk_id"],
            )
        )

        selected_chunks = []
        remaining_budget = (
            request.token_budget
        )

        for candidate in (
            eligible_candidates
        ):
            if (
                len(selected_chunks)
                >= request.top_k
                or remaining_budget <= 0
            ):
                break

            original_content = str(
                candidate.get(
                    "content",
                    "",
                )
            ).strip()

            words = (
                original_content.split()
            )

            truncated = False

            if len(words) > remaining_budget:
                if (
                    selected_chunks
                    or remaining_budget < 20
                ):
                    rejected_candidates.append(
                        {
                            "chunk_id": candidate[
                                "chunk_id"
                            ],
                            "reasons": [
                                "token_budget_exceeded"
                            ],
                        }
                    )

                    continue

                content = " ".join(
                    words[
                        :remaining_budget
                    ]
                )

                truncated = True

            else:
                content = original_content

            token_estimate = (
                _token_estimate(content)
            )

            if token_estimate > remaining_budget:
                continue

            remaining_budget -= (
                token_estimate
            )

            selected_chunks.append(
                {
                    "chunk_id": candidate[
                        "chunk_id"
                    ],
                    "title": candidate.get(
                        "title",
                        "",
                    ),
                    "content": content,
                    "source_system": (
                        candidate.get(
                            "source_system",
                            "",
                        )
                    ),
                    "source_uri": (
                        candidate.get(
                            "source_uri",
                            "",
                        )
                    ),
                    "classification": (
                        candidate.get(
                            "classification",
                            "",
                        )
                    ),
                    "relevance_score": (
                        candidate[
                            "_relevance_score"
                        ]
                    ),
                    "token_estimate": (
                        token_estimate
                    ),
                    "truncated": truncated,
                    "content_sha256": (
                        _sha256_text(
                            original_content
                        )
                    ),
                }
            )

        citations = [
            chunk["chunk_id"]
            for chunk in selected_chunks
        ]

        context_text = "\n\n".join(
            (
                f"[{chunk['chunk_id']}] "
                f"{chunk['title']}\n"
                f"{chunk['content']}"
            )
            for chunk in selected_chunks
        )

        lineage = [
            {
                "citation": chunk[
                    "chunk_id"
                ],
                "source_system": chunk[
                    "source_system"
                ],
                "source_uri": chunk[
                    "source_uri"
                ],
                "content_sha256": chunk[
                    "content_sha256"
                ],
            }
            for chunk in selected_chunks
        ]

        package_identity = json.dumps(
            {
                "question_hash": (
                    _sha256_text(
                        request.question
                    )
                ),
                "user_role": (
                    request.user_role
                ),
                "company_code": (
                    request.company_code
                ),
                "citations": citations,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

        approved = bool(
            selected_chunks
        )

        return {
            "package_id": (
                "CTX-"
                + _sha256_text(
                    package_identity
                )[:16].upper()
            ),
            "created_at_utc": _utc_now(),
            "request": {
                "question_hash": (
                    _sha256_text(
                        request.question
                    )
                ),
                "user_role": (
                    request.user_role
                ),
                "company_code": (
                    request.company_code
                ),
                "top_k": request.top_k,
                "token_budget": (
                    request.token_budget
                ),
            },
            "governance": {
                "status": (
                    "APPROVED"
                    if approved
                    else "BLOCKED"
                ),
                "approved_for_generation": (
                    approved
                ),
                "reason": (
                    "authorized_context_available"
                    if approved
                    else
                    "no_authorized_relevant_context"
                ),
            },
            "citations": citations,
            "context_text": context_text,
            "chunks": selected_chunks,
            "lineage": lineage,
            "rejected_candidates": (
                rejected_candidates
            ),
            "metrics": {
                "candidate_count": len(
                    candidates
                ),
                "authorized_relevant_count": (
                    len(
                        eligible_candidates
                    )
                ),
                "selected_count": len(
                    selected_chunks
                ),
                "token_budget": (
                    request.token_budget
                ),
                "tokens_used": sum(
                    chunk[
                        "token_estimate"
                    ]
                    for chunk
                    in selected_chunks
                ),
            },
        }


    def _blocked_package(
        self,
        request: GovernedContextRequest,
        reason: str,
    ) -> dict[str, Any]:
        return {
            "package_id": (
                "CTX-BLOCKED-"
                + _sha256_text(
                    request.question
                )[:12].upper()
            ),
            "created_at_utc": _utc_now(),
            "request": {
                "question_hash": (
                    _sha256_text(
                        request.question
                    )
                ),
                "user_role": (
                    request.user_role
                ),
                "company_code": (
                    request.company_code
                ),
                "top_k": request.top_k,
                "token_budget": (
                    request.token_budget
                ),
            },
            "governance": {
                "status": "BLOCKED",
                "approved_for_generation": (
                    False
                ),
                "reason": reason,
            },
            "citations": [],
            "context_text": "",
            "chunks": [],
            "lineage": [],
            "rejected_candidates": [],
            "metrics": {
                "candidate_count": 0,
                "authorized_relevant_count": 0,
                "selected_count": 0,
                "token_budget": (
                    request.token_budget
                ),
                "tokens_used": 0,
            },
        }


def load_candidates(
    file_path: str | Path,
) -> list[dict[str, Any]]:
    payload = json.loads(
        Path(file_path).read_text(
            encoding="utf-8"
        )
    )

    if isinstance(payload, list):
        candidates = payload

    elif isinstance(payload, dict):
        candidates = payload.get(
            "candidates",
            [],
        )

    else:
        raise TypeError(
            "Candidate data must be a list "
            "or dictionary."
        )

    if not isinstance(candidates, list):
        raise TypeError(
            "The candidates field must be a list."
        )

    return candidates


def build_context_package(
    question: str,
    user_role: str,
    company_code: str,
    candidates: list[dict[str, Any]],
    top_k: int = 3,
    token_budget: int = 400,
) -> dict[str, Any]:
    request = GovernedContextRequest(
        question=question,
        user_role=user_role,
        company_code=company_code,
        top_k=top_k,
        token_budget=token_budget,
    )

    builder = GovernedContextBuilder()

    return builder.build(
        request=request,
        candidates=candidates,
    )
