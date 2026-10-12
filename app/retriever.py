# DAY 1 — ACTIVITY 4: BASIC POLICY RETRIEVAL MODULE
#
# Purpose:
# Search approved finance policies using words from a user's question.
#
# This is the project's first simple retrieval system.
# Later, we will replace keyword matching with embeddings
# and semantic vector search.

import json
import re
from pathlib import Path


# These common words do not provide useful retrieval meaning.
STOP_WORDS = {
    "the",
    "and",
    "for",
    "from",
    "with",
    "this",
    "that",
    "what",
    "when",
    "where",
    "which",
    "who",
    "can",
    "does",
    "are",
    "above",
}


def load_policies(file_path="data/finance_policies.json"):
    """
    Load approved finance policies from a JSON file.

    Parameters
    ----------
    file_path:
        Location of the synthetic policy file.

    Returns
    -------
    list:
        A list of finance-policy dictionaries.
    """

    policy_path = Path(file_path)

    return json.loads(
        policy_path.read_text(encoding="utf-8")
    )


def tokenize(text):
    """
    Convert text into a set of searchable lowercase words.
    """

    # Extract letters and numbers from the supplied text.
    words = re.findall(r"[a-z0-9]+", text.lower())

    # Remove short and common words.
    return {
        word
        for word in words
        if len(word) > 2 and word not in STOP_WORDS
    }


def retrieve_policies(query, policies, top_k=2):
    """
    Return the policies that best match a user's question.

    Each result includes:
    - The original policy information
    - A simple keyword-match score
    - The terms that matched
    - A source citation
    """

    # Convert the user's question into searchable terms.
    query_terms = tokenize(query)

    results = []

    for policy in policies:

        # Combine the policy fields into one searchable string.
        searchable_text = " ".join(
            [
                policy["title"],
                policy["text"],
                " ".join(policy["keywords"]),
            ]
        )

        # Identify words shared by the query and policy.
        matched_terms = query_terms.intersection(
            tokenize(searchable_text)
        )

        # Only return policies containing at least one matched term.
        if matched_terms:
            results.append(
                {
                    **policy,
                    "retrieval_score": len(matched_terms),
                    "matched_terms": sorted(matched_terms),
                    "citation": (
                        f"{policy['policy_id']} "
                        f"v{policy['version']} — "
                        f"{policy['source']}"
                    ),
                }
            )

    # Put the highest-scoring policy first.
    ranked_results = sorted(
        results,
        key=lambda result: result["retrieval_score"],
        reverse=True,
    )

    # Return only the requested number of results.
    return ranked_results[:top_k]
