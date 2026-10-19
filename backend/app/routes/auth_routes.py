"""Authentication endpoints: register, login, refresh, logout, me."""
import uuid
from datetime import datetime, timezone

from flask import Blueprint, request, current_app
from flask_jwt_extended import (
    create_access_token, create_refresh_token, jwt_required,
    get_jwt_identity, get_jwt,
)

from app.db import get_db
from app.utils.auth_utils import hash_password, check_password, block_token, is_blocked
from app.utils.helpers import oid, serialize


class RevokedJTIError(Exception):
    pass


def _guard_jti():
    """Raise if the current token's JTI is on the logout blocklist."""
    jti = get_jwt()["jti"]
    if is_blocked(jti):
        raise RevokedJTIError("Token has been revoked")

auth_bp = Blueprint("auth", __name__)


def _user_public(u):
    return {
        "id": str(u["_id"]),
        "username": u["username"],
        "email": u.get("email"),
        "display_name": u.get("display_name"),
        "role": u.get("role", "member"),
        "avatar_color": u.get("avatar_color", "#64748b"),
    }


@auth_bp.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""
    email = (data.get("email") or "").strip()
    display_name = (data.get("display_name") or "").strip() or username

    if not username or not password:
        return {"error": "username and password are required"}, 400
    if len(password) < 6:
        return {"error": "password must be at least 6 characters"}, 400
    if not username.isalnum() and "_" not in username:
        return {"error": "username may contain letters, numbers and underscore"}, 400

    role = data.get("role", "member")
    if role not in current_app.config["GLOBAL_ROLES"]:
        role = "member"
    # Only admins may register other admins; public registration cannot mint one.
    if role == "admin":
        role = "member"

    db = get_db()
    if db.users.find_one({"username": username}):
        return {"error": "Username already taken"}, 409

    colors = ["#ef4444", "#f59e0b", "#10b981", "#3b82f6", "#8b5cf6", "#ec4899"]
    doc = {
        "username": username,
        "password_hash": hash_password(password),  # bcrypt — never plain text
        "email": email,
        "display_name": display_name,
        "role": role,
        "avatar_color": colors[len(username) % len(colors)],
        "created_at": datetime.now(timezone.utc),
    }
    res = db.users.insert_one(doc)
    doc["_id"] = res.inserted_id
    user = _user_public(doc)

    access = create_access_token(identity=user["id"], additional_claims={"role": user["role"]})
    refresh = create_refresh_token(identity=user["id"])
    return {"user": user, "access_token": access, "refresh_token": refresh}, 201


@auth_bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""
    db = get_db()
    user = db.users.find_one({"username": username})
    if not user or not check_password(password, user["password_hash"]):
        return {"error": "Invalid credentials"}, 401

    pub = _user_public(user)
    access = create_access_token(identity=pub["id"], additional_claims={"role": pub["role"]})
    refresh = create_refresh_token(identity=pub["id"])
    return {"user": pub, "access_token": access, "refresh_token": refresh}, 200


@auth_bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    identity = get_jwt_identity()
    jti = get_jwt()["jti"]
    _guard_jti()

    db = get_db()
    user = db.users.find_one({"_id": oid(identity)})
    if not user:
        return {"error": "User no longer exists"}, 401

    # Refresh rotation: old refresh JTI is blocked, a new pair is issued.
    block_token(jti, get_jwt()["exp"])
    pub = _user_public(user)
    access = create_access_token(identity=pub["id"], additional_claims={"role": pub["role"]})
    new_refresh = create_refresh_token(identity=pub["id"])
    return {"access_token": access, "refresh_token": new_refresh}, 200


@auth_bp.post("/logout")
@jwt_required(optional=True)
def logout():
    from flask_jwt_extended import decode_token, JWTManager  # local import ok
    blocked_any = False
    # Block the access token JTI if one was sent.
    try:
        claims = get_jwt()
        if claims:
            block_token(claims["jti"], claims["exp"])
            blocked_any = True
    except RuntimeError:
        pass
    # If a refresh token is provided in the body, invalidate it too so the
    # session truly ends (refresh-token invalidation via JTI blocklist).
    body = request.get_json(silent=True) or {}
    rt = body.get("refresh_token")
    if rt:
        try:
            payload = decode_token(rt)
            block_token(payload["jti"], payload["exp"])
            blocked_any = True
        except Exception:
            return {"error": "Invalid refresh token"}, 400
    if not blocked_any:
        return {"error": "Authentication required"}, 401
    return {"message": "Logged out"}, 200


@auth_bp.get("/me")
@jwt_required()
def me():
    _guard_jti()
    db = get_db()
    user = db.users.find_one({"_id": oid(get_jwt_identity())})
    if not user:
        return {"error": "User not found"}, 404
    return {"user": serialize(_user_public(user))}, 200
