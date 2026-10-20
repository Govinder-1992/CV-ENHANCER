# CV Enhancer – Backend (single AWS Lambda)

One AWS Lambda, behind Amazon API Gateway, does the whole job synchronously:

1. **Validate** the uploaded CV (PDF/DOCX, size, magic bytes) and job details.
2. **Extract text** from the CV. The original binary is processed in memory and
   **never written to S3**.
3. **Enhance** the CV with **Amazon Bedrock** (Converse API) — returns an
   analysis (match score, strengths, gaps, suggestions) plus a rewritten CV.
4. **Store** only the enhanced CV + analysis JSON in **S3** (KMS-encrypted) and
   mint a presigned download URL.
5. **Notify** via **Amazon SNS** on completion (and on failure).

## Architecture

```
Browser ──POST /analyze──> API Gateway ──> Lambda (cv-enhancer)
                                              │
                                              ├─ Bedrock (analyze + enhance)
                                              ├─ S3  (enhanced CV + analysis, KMS)
                                              └─ SNS (completion / failure)
                                              └─ SQS DLQ (async failures)
```

## Project layout

```
backend/
├── template.yaml              # SAM: Lambda, API, S3, SNS, KMS, DLQ, IAM
└── src/
    ├── requirements.txt
    ├── app/
    │   ├── handler.py         # Lambda entrypoint (app.handler.lambda_handler)
    │   ├── bedrock_client.py  # Bedrock analyze + enhance
    │   ├── storage.py         # S3 save + presigned URL
    │   └── notifications.py   # SNS publish
    └── common/
        ├── validation.py      # file + field validation
        ├── text_extraction.py # PDF/DOCX -> text
        ├── errors.py          # typed errors -> HTTP status
        ├── logging_utils.py   # structured JSON logging
        └── http.py            # API Gateway responses + CORS
```

## Prerequisites

- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)
  and configured AWS credentials.
- **Bedrock model access**: in the Bedrock console, enable access to the model
  referenced by `BedrockModelId` (default Claude 3.5 Sonnet) in your region.
- Docker (for `sam build --use-container`, recommended so native wheels match
  the Lambda runtime).

## Deploy

```powershell
# from the backend/ folder
sam build --use-container
sam deploy --guided
```

During the guided deploy you'll set parameters:

| Parameter               | Default                                        | Notes                                   |
| ----------------------- | ---------------------------------------------- | --------------------------------------- |
| `StageName`             | `prod`                                         | API stage                               |
| `BedrockModelId`        | `anthropic.claude-3-5-sonnet-20240620-v1:0`    | Must be enabled in your region          |
| `MaxFileSizeMb`         | `5`                                            | Upload size cap                         |
| `CorsAllowOrigin`       | `*`                                            | Set to your site origin in production   |
| `NotificationEmail`     | *(empty)*                                      | If set, subscribes an email to SNS      |
| `DownloadUrlTtlSeconds` | `86400`                                        | Presigned URL lifetime                  |

If you set `NotificationEmail`, confirm the SNS subscription from your inbox.

After deploy, copy the `ApiEndpoint` output into the frontend `config.js` as
`API_ENDPOINT`.

> **API Gateway payload limit:** REST APIs cap the request body at ~10 MB. Since
> the CV is base64-encoded (~33% overhead), keep `MaxFileSizeMb` at 5 or lower.

## Request / response

**Request** (`POST /analyze`, JSON):

```json
{
  "fileName": "cv.pdf",
  "fileType": "pdf",
  "fileContentBase64": "JVBERi0xLjQ...",
  "jobRole": "Senior Frontend Engineer",
  "jobDescription": "We are looking for...",
  "email": "you@example.com"
}
```

**Success** (`200`):

```json
{
  "jobId": "a1b2c3d4-...",
  "status": "completed",
  "downloadUrl": "https://<bucket>.s3...&X-Amz-Signature=...",
  "expiresInSeconds": 86400,
  "analysis": {
    "matchScore": 78,
    "summary": "...",
    "strengths": ["..."],
    "gaps": ["..."],
    "suggestions": ["..."]
  },
  "message": "Your enhanced CV is ready."
}
```

**Errors**: clean JSON with `error` (machine code) and `message`:

- `400 validation_error` / `unsupported_file_type` / `file_too_large`
- `422 text_extraction_failed` (e.g. scanned/image-only PDF)
- `503 transient_error` (Bedrock throttling — safe to retry)
- `500 internal_error`

## Error handling, retries & logging

- **Typed errors** map to HTTP status codes; client errors are logged at
  `WARNING`, unexpected ones at `ERROR` with a full stack trace.
- **Retries**: the Bedrock client uses adaptive retries for throttling. Bedrock
  throttling/5xx surface as `503` so the caller can retry. A **DLQ** is attached
  for any async invocation failures.
- **Logging**: structured JSON lines with a `correlationId` (the Lambda request
  id) tying every log for one request together. Logs land in the function's
  CloudWatch log group (`/aws/lambda/cv-enhancer-<stage>`, 30-day retention).
- **Failure notifications**: when a job id exists, a failure is also published
  to SNS so the user can be told their CV couldn't be processed.

## Security

- **No original CV in S3** — only the enhanced CV + analysis are stored.
- **Encryption**: S3 and SNS use a dedicated **KMS** key (rotation enabled); the
  bucket blocks all public access and denies non-TLS requests.
- **Least-privilege IAM**: the function may only write under `results/*`,
  publish to its SNS topic, invoke the configured Bedrock model, use the KMS
  key, and send to the DLQ.
- **Presigned URLs** expire (`DownloadUrlTtlSeconds`), and results auto-expire
  after 30 days via a lifecycle rule.

## Local test

```powershell
sam local invoke CvEnhancerFunction --event events/analyze.json
```

Create `events/analyze.json` as an API Gateway proxy event whose `body` is the
JSON request above (stringified). Bedrock/S3/SNS calls still hit AWS, so use a
sandbox account.
```
