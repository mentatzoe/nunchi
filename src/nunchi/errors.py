"""Nunchi error types and exit codes."""

EXIT_SUCCESS = 0
EXIT_RUNTIME = 1
EXIT_INPUT = 2
EXIT_VALIDATION = 3


class NunchiError(Exception):
    """Base error for expected Nunchi failures."""

    label = "nunchi error"


class InputError(NunchiError):
    """Raised when input cannot be read or parsed."""

    label = "input error"


class ValidationError(NunchiError):
    """Raised when a V2 contract input is invalid."""

    label = "validation error"
