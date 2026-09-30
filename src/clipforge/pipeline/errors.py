"""Errors that the step chain treats specially (ADR-15)."""

from __future__ import annotations


class PermanentError(Exception):
    """A failure that retrying cannot fix: bad input, no audio, nothing worth clipping.

    `user_message` is shown to the user as is, so keep it short and free of secrets.
    """

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message
