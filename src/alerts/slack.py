"""
Slack alerting utilities for ML drift events.

Reads SLACK_WEBHOOK_URL from environment or Airflow Variable.
Gracefully degrades (logs only) when no webhook is configured.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
import urllib.error
from typing import Any

logger = logging.getLogger(__name__)

# Severity → Slack color mapping
_SEVERITY_COLORS = {
    "ok": "#36a64f",       # green
    "warning": "#ffcc00",  # yellow
    "critical": "#ff0000", # red
}


def _get_webhook_url() -> str | None:
    """Resolve the Slack webhook URL from env or Airflow Variable."""
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if url:
        return url

    # Try Airflow Variable (only available in Airflow runtime)
    try:
        from airflow.models import Variable
        url = Variable.get("SLACK_WEBHOOK_URL", default_var=None)
        return url
    except Exception:
        pass

    return None


def send_slack_alert(
    message: str,
    severity: str = "warning",
    fields: list[dict[str, str]] | None = None,
    webhook_url: str | None = None,
) -> bool:
    """
    Send a formatted Slack alert via incoming webhook.

    Args:
        message:     Main alert message.
        severity:    "ok" | "warning" | "critical" – controls color coding.
        fields:      Optional list of {"title": ..., "value": ...} dicts for rich formatting.
        webhook_url: Override the webhook URL (for testing).

    Returns:
        True if the message was sent successfully, False otherwise.
    """
    url = webhook_url or _get_webhook_url()
    if not url:
        logger.warning(
            "SLACK_WEBHOOK_URL not configured. Alert not sent.\nMessage: %s", message
        )
        return False

    color = _SEVERITY_COLORS.get(severity, _SEVERITY_COLORS["warning"])
    attachment: dict[str, Any] = {
        "color": color,
        "text": message,
        "mrkdwn_in": ["text"],
    }

    if fields:
        attachment["fields"] = [
            {"title": f["title"], "value": f["value"], "short": True}
            for f in fields
        ]

    payload = {"attachments": [attachment]}
    data = json.dumps(payload).encode("utf-8")

    try:
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                logger.info("Slack alert sent: [%s] %s", severity.upper(), message)
                return True
            else:
                logger.error("Slack responded with status %d", resp.status)
                return False
    except urllib.error.URLError as exc:
        logger.error("Failed to send Slack alert: %s", exc)
        return False


def send_drift_alert(verdict: dict, run_date: str, dag_id: str) -> bool:
    """
    Send a structured drift-specific Slack alert from a DriftDecisionEngine verdict.

    Args:
        verdict:  Output of DriftDecisionEngine.evaluate().
        run_date: Airflow logical date.
        dag_id:   Source DAG identifier.

    Returns:
        True if sent successfully.
    """
    status = verdict.get("overall_status", "unknown")
    summary = verdict.get("summary", "")
    feature_verdicts: dict = verdict.get("feature_verdicts", {})

    drifted_features = [f for f, s in feature_verdicts.items() if s != "ok"]

    severity_emoji = {"ok": "✅", "warning": "⚠️", "critical": "🚨"}.get(status, "❓")

    message = (
        f"{severity_emoji} *ML Drift Alert* — `{dag_id}` | `{run_date}`\n"
        f"Status: *{status.upper()}*\n"
        f"{summary}"
    )

    fields = [
        {"title": "Run Date", "value": run_date},
        {"title": "DAG", "value": dag_id},
        {"title": "Drifted Features", "value": ", ".join(drifted_features) or "none"},
        {"title": "Should Retrain", "value": "Yes" if verdict.get("should_retrain") else "No"},
    ]

    return send_slack_alert(message, severity=status, fields=fields)