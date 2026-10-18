"""Safe, provider-neutral AI reviewer failures."""


class AIReviewerError(RuntimeError):
    """Base class for failures with messages safe to return to API callers."""

    code = "ai_review_error"
    safe_message = "AI review could not be completed"

    def __init__(self) -> None:
        super().__init__(self.safe_message)


class AIReviewerNotConfigured(AIReviewerError):
    code = "ai_reviewer_not_configured"
    safe_message = "AI review is not configured"


class AIReviewerInputError(AIReviewerError):
    code = "ai_review_invalid_input"
    safe_message = "AI review input is invalid or exceeds the configured limit"


class AIReviewerTimeout(AIReviewerError):
    code = "ai_provider_timeout"
    safe_message = "AI review provider timed out"


class AIReviewerRateLimited(AIReviewerError):
    code = "ai_provider_rate_limited"
    safe_message = "AI review provider is rate limited or out of quota"


class AIReviewerInvalidResponse(AIReviewerError):
    code = "ai_provider_invalid_response"
    safe_message = "AI review provider returned an invalid response"


class AIReviewerProviderError(AIReviewerError):
    code = "ai_provider_error"
    safe_message = "AI review provider could not complete the request"
