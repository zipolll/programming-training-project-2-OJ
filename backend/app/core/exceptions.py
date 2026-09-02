"""Consistent HTTP and validation error responses."""

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    """Wrap framework HTTP errors in the project response envelope."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "msg": str(exc.detail), "data": None},
    )


async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Use the course-required 400 response without echoing sensitive input."""
    safe_errors = [
        {
            "type": error["type"],
            "loc": error["loc"],
            "msg": error["msg"],
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=400,
        content={"code": 400, "msg": "Invalid request data", "data": safe_errors},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register project-wide exception handlers."""
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
