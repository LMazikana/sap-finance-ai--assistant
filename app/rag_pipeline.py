"""Citation-ready retrieval for the SAP Finance assistant."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any


# Remove common words that do not help distinguish finance topics.
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by",
    "for", "from", "how", "i", "in", "is", "it", "of",
    "on", "or", "the", "to", "what", "when", "where",
    "which", "who", "with",
}


# These roles are used only when a synthetic policy does not
# already contain its own allowed_roles metadata.
DEFAULT_ALLOWED_ROLES = [
    "finance_analyst",
    "finance_manager",
    "controller",
    "internal_auditor",
]


def _tokenize(value: str) -> list[str]:
    """Convert text into normalized retrieval terms."""

    tokens = re.findall(
        r"[a-z0-9]+",
        value.lower(),
    )

    return [
        token
        for token in tokens
        if token not in STOP_WORDS
    ]


def _get_policy_text(policy: dict[str, Any]) -> str:
    """Read policy text from one of the supported field names."""

    for field_name in ("text", "content", "policy_text"):
        value = policy.get(field_name)

        if value:
            return str(value).strip()

    raise ValueError(
        "A policy is missing text, content or policy_text."
    )


def _get_allowed_roles(
    policy: dict[str, Any],
) -> list[str]:
    """Return the roles permitted to retrieve a policy."""

    roles = (
        policy.get("allowed_roles")
        or policy.get("authorized_roles")
        or policy.get("roles")
        or DEFAULT_ALLOWED_ROLES
    )

    # Convert a single role string into a list.
    if isinstance(roles, str):
        roles = [roles]

    return sorted(
        {
            str(role).strip()
            for role in roles
            if str(role).strip()
        }
    )


def chunk_policies(
    policies: list[dict[str, Any]],
    max_words: int = 80,
    overlap_sentences: int = 1,
) -> list[dict[str, Any]]:
    """Create citation-ready chunks from finance policies."""

    chunks: list[dict[str, Any]] = []

    for policy in policies:
        policy_id = str(
            policy.get("policy_id")
            or policy.get("id")
            or "UNKNOWN-POLICY"
        )

        title = str(
            policy.get("title")
            or policy.get("name")
            or policy_id
        )

        policy_text = _get_policy_text(policy)

        citation = str(
            policy.get("citation")
            or policy.get("source")
            or f"data/finance_policies.json#{policy_id}"
        )

        allowed_roles = _get_allowed_roles(policy)

        # Normalize whitespace before sentence splitting.
        clean_text = re.sub(
            r"\s+",
            " ",
            policy_text,
        ).strip()

        sentences = re.split(
            r"(?<=[.!?])\s+",
            clean_text,
        )

        text_groups: list[str] = []
        current_sentences: list[str] = []

        for sentence in sentences:
            candidate = current_sentences + [sentence]
            candidate_words = len(
                " ".join(candidate).split()
            )

            # Close the current chunk before exceeding the target.
            if current_sentences and candidate_words > max_words:
                text_groups.append(
                    " ".join(current_sentences)
                )

                # Keep limited overlap so adjacent chunks retain context.
                if overlap_sentences > 0:
                    current_sentences = current_sentences[
                        -overlap_sentences:
                    ]
                else:
                    current_sentences = []

            current_sentences.append(sentence)

        if current_sentences:
            text_groups.append(
                " ".join(current_sentences)
            )

        # Attach enterprise metadata to every chunk.
        for chunk_number, chunk_text in enumerate(
            text_groups,
            start=1,
        ):
            chunks.append(
                {
                    "chunk_id": (
                        f"{policy_id}-C{chunk_number:03d}"
                    ),
                    "policy_id": policy_id,
                    "title": title,
                    "text": chunk_text,
                    "citation": citation,
                    "allowed_roles": allowed_roles,
                    "source_type": (
                        "synthetic_finance_policy"
                    ),
                }
            )

    return chunks


def retrieve_chunks(
    query: str,
    user_role: str,
    chunks: list[dict[str, Any]],
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """Retrieve relevant chunks after applying role filtering."""

    query_terms = Counter(_tokenize(query))
    ranked_results: list[dict[str, Any]] = []

    for chunk in chunks:
        allowed_roles = chunk.get(
            "allowed_roles",
            [],
        )

        # Security boundary:
        # Exclude unauthorized evidence before scoring it.
        if user_role not in allowed_roles:
            continue

        text_terms = Counter(
            _tokenize(
                f"{chunk['title']} {chunk['text']}"
            )
        )

        title_terms = set(
            _tokenize(chunk["title"])
        )

        # Give one point for matching content terms.
        score = sum(
            min(count, text_terms.get(term, 0))
            for term, count in query_terms.items()
        )

        # Give additional weight to title matches.
        score += 2 * sum(
            1
            for term in query_terms
            if term in title_terms
        )

        # Give additional weight to an explicit policy-ID query.
        if chunk["policy_id"].lower() in query.lower():
            score += 5

        # Do not send irrelevant zero-score evidence onward.
        if score <= 0:
            continue

        result = dict(chunk)
        result["retrieval_score"] = score
        ranked_results.append(result)

    return sorted(
        ranked_results,
        key=lambda item: (
            -item["retrieval_score"],
            item["chunk_id"],
        ),
    )[:top_k]
