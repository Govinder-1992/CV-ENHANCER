"""Worker Lambda for CV Enhancer (SQS triggered).

API Gateway writes the request body directly to SQS (no producer Lambda), so the
message body is the original JSON the browser sent:
  { fileName, fileType, fileContentBase64, jobRole, jobDescription, email }

For each SQS message this function:
  1. Validates the payload and decodes the base64 CV (size + magic-byte checks).
  2. Extracts plain text from the CV (PDF/DOCX). The ORIGINAL binary is never
     written to S3 — only processed in memory.
  3. Calls Amazon Bedrock to analyze + enhance the CV text.
  4. Saves ONLY the enhanced CV + analysis JSON to S3 (KMS-encrypted) and mints
     a presigned download URL.
  5. Publishes a completion notification via Amazon SNS.

Error handling (partial batch responses):
  - Only messages that fail are returned (ReportBatchItemFailures) so they are
    retried; successful ones are deleted from the queue.
  - TransientError (e.g. Bedrock throttling) -> message is returned for retry.
    After maxReceiveCount the queue redrives it to the DLQ.
  - Validation / permanent errors -> a failure notification is sent via SNS and
    the message is treated as handled (not retried) so it can't loop forever.
"""
import json
import os
import uuid

try:
    from app import bedrock_client, notifications, storage
    from common.errors import CvEnhancerError, TransientError, ValidationError
    from common.logging_utils import get_logger, log, set_correlation_id
    from common.text_extraction import extract_text
    from common.validation import validate_payload
except ImportError:  # pragma: no cover - local dev fallback
    from . import bedrock_client, notifications, storage
    from ..common.errors import CvEnhancerError, TransientError, ValidationError
    from ..common.logging_utils import get_logger, log, set_correlation_id
    from ..common.text_extraction import extract_text
    from ..common.validation import validate_payload

logger = get_logger("cv_enhancer.worker")

MAX_FILE_SIZE_MB = int(os.environ.get("MAX_FILE_SIZE_MB", "5"))
MAX_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


def _process_job(record: dict) -> None:
    """Process one SQS record end to end."""
    # API Gateway can forward the original requestId via a message attribute.
    attrs = record.get("messageAttributes", {}) or {}
    request_id = (
        attrs.get("requestId", {}).get("stringValue")
        or record.get("messageId")
        or str(uuid.uuid4())
    )
    set_correlation_id(request_id)

    payload = json.loads(record["body"])
    email = None

    try:
        data = validate_payload(payload, MAX_BYTES)
        email = data["email"]
        log(
            logger, "INFO", "Payload validated",
            requestId=request_id, fileExt=data["fileExt"], fileSize=data["fileSize"],
        )

        # Extract text in memory; the original binary is discarded afterwards.
        cv_text = extract_text(data["fileBytes"], data["fileExt"])
        log(logger, "INFO", "CV text extracted", requestId=request_id, chars=len(cv_text))

        enhanced = bedrock_client.enhance_cv(
            cv_text=cv_text,
            job_role=data["jobRole"],
            job_description=data["jobDescription"],
        )

        metadata = {
            "fileName": data["fileName"],
            "jobRole": data["jobRole"],
            "email": email,
            "correlationId": request_id,
        }
        result = storage.save_results(
            request_id, enhanced["enhancedCv"], enhanced["analysis"], metadata
        )

        notifications.notify_success(
            request_id, email, data["jobRole"], result, enhanced["analysis"]["matchScore"]
        )
        log(logger, "INFO", "Job completed", requestId=request_id)

    except TransientError:
        # Bubble up so SQS retries the message (and eventually redrives to DLQ).
        logger.exception("Transient error; message will be retried")
        raise

    except (ValidationError, CvEnhancerError) as exc:
        # Permanent failure: notify the user and swallow so it isn't retried.
        logger.exception("Permanent error while processing job")
        notifications.notify_failure(request_id, email or "", str(exc))


def lambda_handler(event: dict, context) -> dict:
    """SQS batch handler returning partial batch failures."""
    failures: list[dict] = []

    for record in event.get("Records", []):
        message_id = record.get("messageId")
        try:
            _process_job(record)
        except (KeyError, ValueError):
            # Unparseable body / missing fields: never retry (it won't fix itself).
            logger.exception("Dropping unprocessable SQS message")
            continue
        except Exception:  # noqa: BLE001 - transient/unexpected -> retry this item
            logger.exception("Job failed; reporting for retry")
            if message_id:
                failures.append({"itemIdentifier": message_id})

    # ReportBatchItemFailures: only these messages are made visible again.
    return {"batchItemFailures": failures}
