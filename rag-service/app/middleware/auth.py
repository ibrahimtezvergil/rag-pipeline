from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import get_settings


EXEMPT_PATHS = {
    "/",
    "/health",
    "/docs",
    "/docs/oauth2-redirect",
    "/openapi.json",
    "/redoc",
}


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        api_key = request.headers.get("X-API-Key")
        application_id = request.headers.get("X-Application-ID") or request.headers.get("X-Project-ID")
        if not api_key or not application_id:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing authentication headers"},
            )

        if api_key not in get_settings().api_keys_set:
            return JSONResponse(
                status_code=403,
                content={"detail": "Invalid API key"},
            )

        request.state.api_key = api_key
        request.state.application_id = application_id
        return await call_next(request)
