from urllib.parse import quote

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from app.auth_utils import SESSION_COOKIE, load_session_token
from app.db import SessionLocal
from app.models import User, UserStatus

ALLOWED_WITHOUT_AUTH = {"/login", "/register"}
ALLOWED_PENDING = {"/pending", "/logout"}


class AuthRedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        if path.startswith("/static") or path == "/manifest.webmanifest":
            return await call_next(request)

        if path in ALLOWED_WITHOUT_AUTH:
            return await call_next(request)

        if path.startswith("/invite/") and request.method == "GET":
            token = request.cookies.get(SESSION_COOKIE)
            if not token:
                safe_next = quote(path, safe="/")
                return RedirectResponse(f"/login?next={safe_next}", status_code=303)

        if request.method == "POST" and path == "/logout":
            return await call_next(request)

        token = request.cookies.get(SESSION_COOKIE)
        if not token or not _wants_html(request):
            if not token and _wants_html(request):
                return RedirectResponse("/login", status_code=303)
            return await call_next(request)

        user_id = load_session_token(token)
        if user_id is None:
            return RedirectResponse("/login", status_code=303)

        db = SessionLocal()
        try:
            user = db.get(User, user_id)
            if not user:
                return RedirectResponse("/login", status_code=303)

            if path in ALLOWED_PENDING:
                return await call_next(request)

            if user.status == UserStatus.pending:
                return RedirectResponse("/pending", status_code=303)
            if user.status == UserStatus.rejected:
                return RedirectResponse("/login?error=rejected", status_code=303)
        finally:
            db.close()

        return await call_next(request)


def _wants_html(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "text/html" in accept or request.method == "GET"
