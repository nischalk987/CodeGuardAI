"""Domain exceptions that do not depend on an API framework."""


class InvalidReviewTransition(ValueError):
    """Raised when a review attempts a lifecycle transition that is not allowed."""
