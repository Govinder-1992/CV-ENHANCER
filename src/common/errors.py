"""Shared exception types for the CV Enhancer backend."""


class CvEnhancerError(Exception):
    """Base class for application errors."""

    #: HTTP status to surface when this error reaches the API layer.
    status_code = 500
    #: Stable machine-readable code for the client.
    code = "internal_error"


class ValidationError(CvEnhancerError):
    status_code = 400
    code = "validation_error"


class UnsupportedFileTypeError(ValidationError):
    code = "unsupported_file_type"


class FileTooLargeError(ValidationError):
    code = "file_too_large"


class TextExtractionError(CvEnhancerError):
    status_code = 422
    code = "text_extraction_failed"


class BedrockError(CvEnhancerError):
    """Raised when the Bedrock analysis/enhancement call fails."""

    code = "bedrock_error"


class TransientError(CvEnhancerError):
    """Retryable error. In the worker this triggers an SQS redrive."""

    code = "transient_error"
