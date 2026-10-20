"""S3 persistence + presigned download links for enhanced CVs and analysis.

The ORIGINAL CV is never stored. Only the Bedrock-generated enhanced CV and the
analysis JSON are written to S3.
"""
import json
import os

import boto3
from botocore.config import Config

try:
    from common.logging_utils import get_logger, log
except ImportError:  # pragma: no cover
    from ..common.logging_utils import get_logger, log

logger = get_logger("cv_enhancer.storage")

RESULTS_BUCKET = os.environ["RESULTS_BUCKET"]
DOWNLOAD_URL_TTL = int(os.environ.get("DOWNLOAD_URL_TTL_SECONDS", "86400"))  # 24h

_s3 = boto3.client("s3", config=Config(signature_version="s3v4", retries={"max_attempts": 3}))


def _put(key: str, body: bytes, content_type: str) -> None:
    # AES256 (SSE-S3) matches the bucket's default encryption and policy.
    _s3.put_object(
        Bucket=RESULTS_BUCKET,
        Key=key,
        Body=body,
        ContentType=content_type,
        ServerSideEncryption="AES256",
    )


def save_results(job_id: str, enhanced_cv: str, analysis: dict, metadata: dict) -> dict:
    """Store the enhanced CV (txt) and analysis (json); return keys + a link."""
    prefix = f"results/{job_id}"
    cv_key = f"{prefix}/enhanced-cv.txt"
    analysis_key = f"{prefix}/analysis.json"

    _put(cv_key, enhanced_cv.encode("utf-8"), "text/plain; charset=utf-8")

    analysis_doc = {
        "jobId": job_id,
        "metadata": metadata,
        "analysis": analysis,
    }
    _put(analysis_key, json.dumps(analysis_doc, indent=2).encode("utf-8"), "application/json")

    download_url = _s3.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": RESULTS_BUCKET,
            "Key": cv_key,
            "ResponseContentDisposition": 'attachment; filename="enhanced-cv.txt"',
        },
        ExpiresIn=DOWNLOAD_URL_TTL,
    )

    log(logger, "INFO", "Results saved to S3", cvKey=cv_key, analysisKey=analysis_key)
    return {
        "cvKey": cv_key,
        "analysisKey": analysis_key,
        "downloadUrl": download_url,
        "expiresInSeconds": DOWNLOAD_URL_TTL,
    }
