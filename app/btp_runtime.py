"""SAP BTP Cloud Foundry runtime for the Finance assistant."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from flask import Flask, jsonify


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_GATE_PATH = (
    "governance/day16_release_gate.json"
)


def resolve_gate_path(
    supplied_path: str | Path | None = None,
) -> Path:
    """Resolve the governance-gate path safely."""

    raw_path = supplied_path or os.getenv(
        "GOVERNANCE_GATE_PATH",
        DEFAULT_GATE_PATH,
    )

    gate_path = Path(raw_path)

    if not gate_path.is_absolute():
        gate_path = PROJECT_ROOT / gate_path

    return gate_path.resolve()


def read_release_gate(
    supplied_path: str | Path | None = None,
) -> dict[str, Any]:
    """Load and validate the deployment release gate."""

    gate_path = resolve_gate_path(supplied_path)

    if not gate_path.exists():
        return {
            "ready": False,
            "reason": "governance_gate_missing",
            "decision": "UNKNOWN",
            "checks_passed": 0,
            "checks_total": 0,
            "gate_digest": None,
        }

    try:
        gate = json.loads(
            gate_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return {
            "ready": False,
            "reason": "governance_gate_invalid",
            "decision": "UNKNOWN",
            "checks_passed": 0,
            "checks_total": 0,
            "gate_digest": None,
        }

    checks = gate.get("checks", {})

    checks_passed = sum(
        bool(value) for value in checks.values()
    )

    checks_total = len(checks)

    decision = gate.get("decision", "UNKNOWN")

    ready = (
        decision == "APPROVED_FOR_LOCAL_DEMO"
        and checks_total > 0
        and checks_passed == checks_total
    )

    canonical_gate = json.dumps(
        gate,
        sort_keys=True,
        separators=(",", ":"),
    )

    gate_digest = hashlib.sha256(
        canonical_gate.encode("utf-8")
    ).hexdigest()[:16]

    return {
        "ready": ready,
        "reason": (
            "governance_gate_passed"
            if ready
            else "governance_gate_blocked"
        ),
        "decision": decision,
        "checks_passed": checks_passed,
        "checks_total": checks_total,
        "gate_digest": gate_digest,
    }


def create_app(
    gate_path: str | Path | None = None,
) -> Flask:
    """Create the governed Flask application."""

    app = Flask(__name__)

    @app.after_request
    def add_security_headers(response):
        """Add basic API-response security headers."""

        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/")
    def service_information():
        """Return non-sensitive service metadata."""

        return jsonify(
            {
                "service": "governed-sap-finance-assistant",
                "runtime": "sap-btp-cloud-foundry",
                "version": "day17",
            }
        )

    @app.get("/health")
    def health():
        """Liveness check: confirm the process is running."""

        return (
            jsonify(
                {
                    "status": "alive",
                    "service": (
                        "governed-sap-finance-assistant"
                    ),
                }
            ),
            200,
        )

    @app.get("/ready")
    def ready():
        """Readiness check: enforce the governance gate."""

        gate_status = read_release_gate(gate_path)

        http_status = (
            200 if gate_status["ready"] else 503
        )

        return (
            jsonify(
                {
                    "status": (
                        "ready"
                        if gate_status["ready"]
                        else "not_ready"
                    ),
                    "reason": gate_status["reason"],
                    "release_decision": (
                        gate_status["decision"]
                    ),
                    "checks_passed": (
                        gate_status["checks_passed"]
                    ),
                    "checks_total": (
                        gate_status["checks_total"]
                    ),
                    "gate_digest": (
                        gate_status["gate_digest"]
                    ),
                }
            ),
            http_status,
        )

    @app.get("/api/v1/governance/status")
    def governance_status():
        """Return sanitized governance status."""

        gate_status = read_release_gate(gate_path)

        return (
            jsonify(
                {
                    "ready": gate_status["ready"],
                    "release_decision": (
                        gate_status["decision"]
                    ),
                    "gate_digest": (
                        gate_status["gate_digest"]
                    ),
                }
            ),
            200,
        )

    return app


# Gunicorn imports this application object.
app = create_app()


if __name__ == "__main__":
    # Cloud Foundry supplies PORT dynamically.
    port = int(os.getenv("PORT", "8080"))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
    )
