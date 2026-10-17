"""Service-layer errors; main.py maps them to HTTP responses."""


class ServiceError(Exception):
    status_code = 400

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class NotFound(ServiceError):
    status_code = 404


class Conflict(ServiceError):
    status_code = 409


class Forbidden(ServiceError):
    status_code = 403


class Unauthorized(ServiceError):
    status_code = 401


class TooManyRequests(ServiceError):
    status_code = 429
