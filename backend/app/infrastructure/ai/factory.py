"""Construct the configured provider without coupling callers to an adapter."""

from app.ai.exceptions import AIReviewerNotConfigured
from app.ai.reviewer import AIReviewer
from app.core.config import Settings
from app.infrastructure.ai.groq_reviewer import GroqAIReviewer
from app.infrastructure.ai.huggingface_reviewer import HuggingFaceAIReviewer


def create_ai_reviewer(settings: Settings) -> AIReviewer:
    """Return the configured reviewer, failing safely when its backend secret is missing."""
    if settings.ai_provider == "groq":
        if settings.groq_api_key is None:
            raise AIReviewerNotConfigured()
        return GroqAIReviewer(settings)
    if settings.hf_token is None:
        raise AIReviewerNotConfigured()
    return HuggingFaceAIReviewer(settings)


def configured_provider(settings: Settings) -> tuple[str, str]:
    """Return display name and model ID for safe CLI provenance (never a credential)."""
    if settings.ai_provider == "groq":
        return "Groq", settings.groq_model
    return "Hugging Face", settings.hf_model
