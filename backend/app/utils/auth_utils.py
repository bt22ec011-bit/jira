"""Auth utilities: bcrypt hashing, JWT extras, role_required decorator."""
from functools import wraps

import bcrypt
from flask_jwt_extended import verify_jwt_in_request, get_jwt, get_jwt_identity

from app.db import get_db


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def check_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def is_blocked(jti: str) -> bool:
    db = get_db()
    # purge expired entries opportunistically
    db.token_blocklist.delete_many({"expired": True})
    return db.token_blocklist.find_one({"jti": jti}) is not None


def block_token(jti: str, exp: int):
    db = get_db()
    db.token_blocklist.update_one(
        {"jti": jti}, {"$set": {"jti": jti, "exp": exp, "expired": False}}, upsert=True
    )


def role_required(*roles):
    """Custom decorator guarding privileged routes on top of JWT auth.

    Usage: @role_required("admin")
    Checks the `role` claim carried by the access token.
    """
    def wrapper(fn):
        @wraps(fn)
        def handler(*args, **kwargs):
            verify_jwt_in_request()
            claims = get_jwt()
            if claims.get("role") not in roles:
                return {"error": "Insufficient role", "allowed": list(roles)}, 403
            return fn(*args, **kwargs)
        return handler
    return wrapper


def current_user_id() -> str:
    return str(get_jwt_identity())


def current_role() -> str:
    return get_jwt().get("role", "")
