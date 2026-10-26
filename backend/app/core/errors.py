"""Domain errors raised by the service layer; main.py maps them to HTTP responses."""


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, **details):
        """Store the error message and any extra details to send back in the JSON response."""
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class DatasetFormatError(AppError):
    """The file cannot be read as a tracking dataset at all (no header, missing columns, ...)."""
    status_code = 422
    code = "invalid_dataset"
