"""Amazon SNS success / failure notifications for CV Enhancer.

Design goals (per requirements):
  * One SNS topic the worker publishes to after processing succeeds or fails.
  * Each user is emailed at THEIR OWN address, not a single shared inbox. This
    is done with per-user email subscriptions plus a subscription filter policy
    so a message tagged with an email is only delivered to that subscriber.
  * "Verified email": SNS email subscriptions require the recipient to click a
    confirmation link before AWS will deliver anything, so unverified addresses
    simply never receive mail.
  * No sensitive CV content in emails — only status, role, match score, and a
    short-lived secure download link.
  * Robust error handling + logging; a notification failure never breaks the job.
"""
import json
import os

import boto3
from botocore.config import Config

try:
    from common.logging_utils import get_logger, log
except ImportError:  # pragma: no cover
    from ..common.logging_utils import get_logger, log

logger = get_logger("cv_enhancer.notifications")

TOPIC_ARN = os.environ["NOTIFICATION_TOPIC_ARN"]

_sns = boto3.client("sns", config=Config(retries={"max_attempts": 3, "mode": "standard"}))


def _ensure_subscription(email: str) -> str:
    """Ensure an email subscription exists for this address (idempotent).

    Returns one of: "confirmed", "pending", "unavailable". If a subscription is
    still pending the user hasn't verified their address yet, so no email will
    be delivered for this run — that is expected on a user's first request.
    """
    try:
        paginator = _sns.get_paginator("list_subscriptions_by_topic")
        for page in paginator.paginate(TopicArn=TOPIC_ARN):
            for sub in page.get("Subscriptions", []):
                if sub.get("Protocol") == "email" and sub.get("Endpoint") == email:
                    arn = sub.get("SubscriptionArn", "")
                    if arn.startswith("arn:"):
                        return "confirmed"
                    return "pending"  # "PendingConfirmation"

        # No subscription yet: create one with a filter policy scoped to this
        # email so the user only ever receives their own notifications. SNS
        # emails the user a confirmation link (the verification step).
        _sns.subscribe(
            TopicArn=TOPIC_ARN,
            Protocol="email",
            Endpoint=email,
            Attributes={"FilterPolicy": json.dumps({"email": [email]})},
            ReturnSubscriptionArn=True,
        )
        log(logger, "INFO", "Created SNS email subscription (pending confirmation)", email=email)
        return "pending"
    except Exception:  # noqa: BLE001 - never let subscription issues break the job
        logger.exception("Could not ensure SNS subscription")
        return "unavailable"


def _publish(subject: str, message: dict, email: str, status: str) -> None:
    """Publish to the topic, tagging the email so the filter policy routes it."""
    _sns.publish(
        TopicArn=TOPIC_ARN,
        Subject=subject[:100],  # SNS subject hard limit.
        Message=json.dumps(message, default=str),
        MessageAttributes={
            "status": {"DataType": "String", "StringValue": status},
            # Routing key for the per-user subscription filter policy.
            "email": {"DataType": "String", "StringValue": email},
        },
    )


def notify_success(request_id: str, email: str, job_role: str, result: dict, match_score: int) -> None:
    """Email the user that their enhanced CV is ready, with a secure link.

    The message deliberately contains NO CV text — only status metadata and a
    short-lived presigned download URL.
    """
    sub_state = _ensure_subscription(email)

    ttl_hours = max(1, int(result.get("expiresInSeconds", 0)) // 3600)
    message = {
        "status": "completed",
        "requestId": request_id,
        "jobRole": job_role,
        "matchScore": match_score,
        "downloadUrl": result["downloadUrl"],
        "linkValidForHours": ttl_hours,
        "message": (
            "Your enhanced CV is ready. Use the secure link below to download it. "
            f"The link expires in about {ttl_hours} hour(s)."
        ),
    }
    try:
        _publish(f"Your enhanced CV for '{job_role}' is ready", message, email, "completed")
        log(
            logger, "INFO", "Success notification published",
            requestId=request_id, subscriptionState=sub_state,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Could not publish success notification")


def notify_failure(request_id: str, email: str, reason: str) -> None:
    """Email the user that processing failed. No CV content is included."""
    if not email:
        log(logger, "WARNING", "No email on job; skipping failure notification", requestId=request_id)
        return

    sub_state = _ensure_subscription(email)
    message = {
        "status": "failed",
        "requestId": request_id,
        "message": "We couldn't process your CV. Please try again.",
        # A short, non-sensitive reason only.
        "reason": reason[:200] if reason else "unknown_error",
    }
    try:
        _publish("CV Enhancer: processing failed", message, email, "failed")
        log(
            logger, "INFO", "Failure notification published",
            requestId=request_id, subscriptionState=sub_state,
        )
    except Exception:  # noqa: BLE001 - never mask the original error
        logger.exception("Could not publish failure notification")
