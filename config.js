/**
 * CV Enhancer – runtime configuration.
 *
 * Replace API_ENDPOINT with your Amazon API Gateway invoke URL, e.g.
 *   https://abc123.execute-api.us-east-1.amazonaws.com/prod/analyze-cv
 *
 * The frontend sends the CV (base64-encoded in JSON) plus the job details to
 * this endpoint. The original CV is NOT uploaded directly to Amazon S3 from the
 * browser — API Gateway (and whatever Lambda/backend sits behind it) is
 * responsible for any storage.
 */
window.CV_ENHANCER_CONFIG = {
  // Amazon API Gateway endpoint that accepts the analyze request.
  // Use the 'ApiEndpoint' value from the SAM deploy outputs (ends in /analyze-cv).
  API_ENDPOINT: "https://4ay7x86f00.execute-api.us-east-1.amazonaws.com/prod/analyze-cv",

  // API key for the 'x-api-key' header. Required only if you deployed with
  // AuthMode=API_KEY; leave empty for the default public (NONE) mode.
  API_KEY: "",

  // Client-side upload limits.
  // IMPORTANT: API Gateway forwards the request straight into an SQS message,
  // and SQS caps a message at 256 KB. The CV is base64-encoded (~33% overhead)
  // and wrapped in JSON alongside the job description, so the raw file must stay
  // well under that. 0.18 MB (~180 KB) is a safe ceiling. Raising this will make
  // larger uploads fail at the gateway with a queueing error.
  MAX_FILE_SIZE_MB: 0.18,
  ALLOWED_EXTENSIONS: ["pdf", "docx"],

  // Polling for async processing. If your API returns a 'statusUrl' or 'jobId',
  // the frontend will poll until the enhanced CV is ready.
  POLL_INTERVAL_MS: 3000,
  POLL_MAX_ATTEMPTS: 40, // ~2 minutes at 3s intervals
};
