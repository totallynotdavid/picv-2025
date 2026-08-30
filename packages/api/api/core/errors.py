__all__ = ["TransientInfraError"]


class TransientInfraError(Exception):
    """An infrastructure error that is safe to retry."""
