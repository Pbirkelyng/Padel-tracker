import bcrypt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import get_settings

SESSION_COOKIE = "padel_session"

# bcrypt has a 72-byte input limit; truncate to be safe with long passwords.
_BCRYPT_MAX_BYTES = 72


def _encode(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_encode(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_encode(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def _serializer() -> URLSafeTimedSerializer:
    settings = get_settings()
    return URLSafeTimedSerializer(settings.secret_key, salt="padel-session")


def create_session_token(user_id: int) -> str:
    return _serializer().dumps({"user_id": user_id})


def load_session_token(token: str) -> int | None:
    settings = get_settings()
    max_age = settings.session_max_age_days * 86400
    try:
        data = _serializer().loads(token, max_age=max_age)
        return int(data["user_id"])
    except (BadSignature, SignatureExpired, KeyError, ValueError, TypeError):
        return None

