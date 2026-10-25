"""Единый JSON-формат ошибок для фронтенда."""
import uuid
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiProblem(Exception):
    def __init__(self, status_code: int, code: str, message: str, details=None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def _error(request: Request, status_code: int, code: str, message: str, details=None):
    return JSONResponse(
        status_code=status_code,
        content={
            'code': code,
            'message': message,
            'details': details or {},
            'request_id': getattr(request.state, 'request_id', str(uuid.uuid4())),
        },
    )


def install_error_handlers(app: FastAPI):
    @app.exception_handler(ApiProblem)
    async def api_problem(request: Request, exc: ApiProblem):
        return _error(request, exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(HTTPException)
    async def http_problem(request: Request, exc: HTTPException):
        labels = {401: 'UNAUTHORIZED', 403: 'FORBIDDEN', 404: 'NOT_FOUND', 409: 'INVALID_STATE_TRANSITION'}
        return _error(request, exc.status_code, labels.get(exc.status_code, 'HTTP_ERROR'), str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_problem(request: Request, exc: RequestValidationError):
        fields = [{'field': '.'.join(str(x) for x in item['loc']), 'message': item['msg']}
                  for item in exc.errors()]
        return _error(request, 422, 'VALIDATION_ERROR', 'Проверьте заполнение полей', {'fields': fields})
