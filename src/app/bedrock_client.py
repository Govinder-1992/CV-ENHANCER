"""Amazon Bedrock wrapper that analyzes and enhances a CV.

Uses the Bedrock Runtime Converse API, which gives a single, model-agnostic
interface across Anthropic Claude, Amazon Nova, and others. The model id is
configurable via the BEDROCK_MODEL_ID environment variable.
"""
import json
import os

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

try:
    from common.errors import BedrockError, TransientError
    from common.logging_utils import get_logger, log
except ImportError:  # pragma: no cover
    from ..common.errors import BedrockError, TransientError
    from ..common.logging_utils import get_logger, log

logger = get_logger("cv_enhancer.bedrock")

MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v1:0")
MAX_TOKENS = int(os.environ.get("BEDROCK_MAX_TOKENS", "4000"))
TEMPERATURE = float(os.environ.get("BEDROCK_TEMPERATURE", "0.3"))

# Bedrock throttling / server errors that are worth retrying via SQS-less retry.
_TRANSIENT_CODES = {"ThrottlingException", "ModelTimeoutException", "ServiceUnavailableException",
                    "InternalServerException", "ModelNotReadyException"}

_bedrock = boto3.client(
    "bedrock-runtime",
    config=Config(retries={"max_attempts": 4, "mode": "adaptive"}, read_timeout=120),
)

_SYSTEM_PROMPT = (
    "You are an expert career coach, ATS (applicant tracking system) specialist, "
    "and professional CV writer. You analyze a CV against a specific target role "
    "and job description, then rewrite it to be tailored to that role using strong "
    "action verbs, quantified achievements, and clear structure.\n\n"
    "STRICT TRUTHFULNESS RULES — these override everything else:\n"
    "- Preserve the candidate's ACTUAL qualifications and work experience exactly: "
    "do not invent, add, or exaggerate employers, job titles, dates, degrees, "
    "certifications, metrics, or responsibilities that are not supported by the "
    "original CV.\n"
    "- You MAY rephrase, reorganize, and emphasize existing content, and surface "
    "skills the candidate genuinely demonstrates, but never fabricate new facts.\n"
    "- If the job needs something the candidate lacks, list it as a gap/missing "
    "skill rather than adding it to the enhanced CV as if they already have it."
)

_USER_TEMPLATE = """Target job role: {job_role}

Job description:
\"\"\"
{job_description}
\"\"\"

Original CV text:
\"\"\"
{cv_text}
\"\"\"

Analyze the CV against the job requirements, then return a SINGLE JSON object
(no markdown, no code fences) with EXACTLY these keys:
- "matchScore": integer 0-100, how well the original CV fits the target role.
- "summary": 2-3 sentence overview of the candidate's fit for this role.
- "strengths": array of short strings — the candidate's most relevant existing strengths.
- "missingSkills": array of short strings — skills/experience the job asks for that
  are absent or weak in the CV.
- "recommendedKeywords": array of short strings — important keywords/phrases from the
  job description the CV should include for ATS matching (only ones the candidate can
  truthfully support or that belong in a skills/summary section).
- "gaps": array of short strings — broader gaps vs the job requirements.
- "suggestions": array of specific, actionable improvements the candidate should make.
- "enhancedCv": the full rewritten CV as plain text, tailored to the target role,
  preserving the candidate's real history and qualifications.

Respond with JSON only."""


def _extract_json(text: str) -> dict:
    """Parse the model output into a dict, tolerating stray fences/prose."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        # Drop a leading 'json' language hint if present.
        if text[:4].lower() == "json":
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise BedrockError("Model did not return parseable JSON.")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise BedrockError(f"Could not parse model JSON: {exc}") from exc


def enhance_cv(cv_text: str, job_role: str, job_description: str) -> dict:
    """Call Bedrock and return a normalized analysis + enhanced CV dict."""
    prompt = _USER_TEMPLATE.format(
        job_role=job_role, job_description=job_description, cv_text=cv_text
    )

    try:
        result = _bedrock.converse(
            modelId=MODEL_ID,
            system=[{"text": _SYSTEM_PROMPT}],
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": MAX_TOKENS, "temperature": TEMPERATURE},
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        log(logger, "ERROR", "Bedrock call failed", errorCode=code)
        if code in _TRANSIENT_CODES:
            raise TransientError(f"Bedrock transient error: {code}") from exc
        raise BedrockError(f"Bedrock error: {code}") from exc
    except Exception as exc:  # noqa: BLE001
        raise TransientError(f"Bedrock call failed: {exc}") from exc

    try:
        text = result["output"]["message"]["content"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise BedrockError("Unexpected Bedrock response shape.") from exc

    parsed = _extract_json(text)

    enhanced_cv = parsed.get("enhancedCv")
    if not isinstance(enhanced_cv, str) or not enhanced_cv.strip():
        raise BedrockError("Model response is missing the enhanced CV text.")

    # Normalize the analysis block with safe defaults.
    def _as_list(value):
        return [str(v) for v in value] if isinstance(value, list) else []

    analysis = {
        "matchScore": int(parsed.get("matchScore", 0)) if str(parsed.get("matchScore", "")).strip().isdigit() else 0,
        "summary": str(parsed.get("summary", "")),
        "strengths": _as_list(parsed.get("strengths")),
        "missingSkills": _as_list(parsed.get("missingSkills")),
        "recommendedKeywords": _as_list(parsed.get("recommendedKeywords")),
        "gaps": _as_list(parsed.get("gaps")),
        "suggestions": _as_list(parsed.get("suggestions")),
    }

    usage = result.get("usage", {})
    log(
        logger, "INFO", "Bedrock enhancement complete",
        modelId=MODEL_ID, inputTokens=usage.get("inputTokens"),
        outputTokens=usage.get("outputTokens"), matchScore=analysis["matchScore"],
    )

    return {"analysis": analysis, "enhancedCv": enhanced_cv}
