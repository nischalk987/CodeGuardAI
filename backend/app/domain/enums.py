"""Closed vocabularies for review and finding state."""

from enum import Enum


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ReviewStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ReviewSourceType(str, Enum):
    SNIPPET = "snippet"
    DIFF = "diff"
    PULL_REQUEST = "pull_request"
    DEMO = "demo"


class FindingSource(str, Enum):
    STATIC = "static"
    AI = "ai"


class FindingStatus(str, Enum):
    OPEN = "open"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"
    FIXED = "fixed"


class EvidenceCertainty(str, Enum):
    """Whether a finding is supported by verified evidence or remains a hypothesis."""

    CONFIRMED = "confirmed"
    HYPOTHESIS = "hypothesis"
