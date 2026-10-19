"""Project CRUD, member management and labels.

Permissions:
- Admin: create projects, manage any project's members/settings.
- Project owner (creator): manage own project's members/settings.
- Members: view the project and its issues.
- Reporters (per-project role "reporter"): view + raise issues only.
"""
import re

from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity

from app.db import get_db
from app.utils.helpers import oid, serialize, find_project, get_membership, can_view_project
from app.utils.auth_utils import role_required

projects_bp = Blueprint("projects", __name__)
KEY_RE = re.compile(r"^[A-Z][A-Z0-9]{1,9}$")


def _actor():
    return str(get_jwt_identity()), get_jwt().get("role", "member")


@projects_bp.get("")
@jwt_required()
def list_projects():
    """Projects visible to the caller: owned or joined (all for admin). Paginated."""
    db = get_db()
    uid, role = _actor()
    page = max(int(request.args.get("page", 1)), 1)
    per_page = min(max(int(request.args.get("per_page", 20)), 1), 100)

    if role == "admin":
        query = {}
    else:
        query = {"$or": [{"owner_id": oid(uid)}, {"members.user_id": oid(uid)}]}

    total = db.projects.count_documents(query)
    docs = list(
        db.projects.find(query)
        .sort("created_at", -1)
        .skip((page - 1) * per_page)
        .limit(per_page)
    )
    items = []
    for p in docs:
        d = serialize(p)
        d["my_role"] = (get_membership(p, uid) or {}).get("role") if role != "admin" else "admin"
        items.append(d)
    return {"items": items, "total": total, "page": page, "per_page": per_page}, 200


@projects_bp.post("")
@role_required("admin")
def create_project():
    """Only admins may create projects (spec: 'Admin: Creates projects')."""
    data = request.get_json(silent=True) or {}
    key = (data.get("key") or "").strip().upper()
    name = (data.get("name") or "").strip()
    description = (data.get("description") or "").strip()

    if not KEY_RE.match(key):
        return {"error": "Project key must be 2-10 uppercase alphanumeric chars"}, 400
    if not name:
        return {"error": "Project name is required"}, 400

    db = get_db()
    if db.projects.find_one({"key": key}):
        return {"error": f"Project key '{key}' already exists"}, 409

    owner_id = data.get("owner_id")
    uid, _ = _actor()
    owner = oid(owner_id) or oid(uid)
    if not db.users.find_one({"_id": owner}):
        return {"error": "Owner user not found"}, 400

    from datetime import datetime, timezone
    doc = {
        "key": key,
        "name": name,
        "description": description,
        "owner_id": owner,
        "members": [],
        "next_issue_num": 1,
        # workflow config lives in app/config.py; stored per project so an
        # admin could later customise it (basic model keeps defaults)
        "workflow": None,
        "created_at": datetime.now(timezone.utc),
    }
    res = db.projects.insert_one(doc)
    doc["_id"] = res.inserted_id
    return {"project": serialize(doc)}, 201


@projects_bp.get("/<pid>")
@jwt_required()
def get_project(pid):
    db = get_db()
    project = find_project(pid)
    if not project:
        return {"error": "Project not found"}, 404
    uid, role = _actor()
    if not can_view_project(project, uid, role):
        return {"error": "You are not a member of this project"}, 403
    out = serialize(project)
    out["my_role"] = (get_membership(project, uid) or {}).get("role") or ("admin" if role == "admin" else None)
    # enrich members with display info
    ids = [oid(m["user_id"]) for m in project.get("members", [])]
    users = {str(u["_id"]): u for u in db.users.find({"_id": {"$in": ids}})}
    for m in out["members"]:
        u = users.get(str(m["user_id"]))
        if u:
            m["display_name"] = u.get("display_name")
            m["username"] = u.get("username")
            m["avatar_color"] = u.get("avatar_color")
    return {"project": out}, 200


@projects_bp.put("/<pid>")
@jwt_required()
def update_project(pid):
    project = find_project(pid)
    if not project:
        return {"error": "Project not found"}, 404
    uid, role = _actor()
    if role != "admin" and str(project["owner_id"]) != uid:
        return {"error": "Only the owner or an admin can edit this project"}, 403
    data = request.get_json(silent=True) or {}
    changes = {}
    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return {"error": "name cannot be empty"}, 400
        changes["name"] = name
    if "description" in data:
        changes["description"] = (data.get("description") or "").strip()
    if not changes:
        return {"error": "No valid fields to update"}, 400
    get_db().projects.update_one({"_id": project["_id"]}, {"$set": changes})
    return {"project": serialize(find_project(pid))}, 200


@projects_bp.post("/<pid>/members")
@jwt_required()
def add_member(pid):
    project = find_project(pid)
    if not project:
        return {"error": "Project not found"}, 404
    uid, role = _actor()
    if role != "admin" and str(project["owner_id"]) != uid:
        return {"error": "Only the owner or an admin can manage members"}, 403

    data = request.get_json(silent=True) or {}
    target = (data.get("user_id") or "").strip()
    prole = data.get("role", "member")
    from flask import current_app
    if prole not in current_app.config["PROJECT_ROLES"]:
        return {"error": f"role must be one of {current_app.config['PROJECT_ROLES']}"}, 400

    db = get_db()
    user = db.users.find_one({"_id": oid(target)})
    if not user:
        return {"error": "User not found"}, 404
    if str(user["_id"]) == str(project["owner_id"]):
        return {"error": "Owner is already a member"}, 409
    if get_membership(project, target):
        return {"error": "User is already a member"}, 409

    db.projects.update_one(
        {"_id": project["_id"]},
        {"$push": {"members": {"user_id": str(user["_id"]), "role": prole}}},
    )
    return {"project": serialize(find_project(pid))}, 201


@projects_bp.delete("/<pid>/members/<user_id>")
@jwt_required()
def remove_member(pid, user_id):
    project = find_project(pid)
    if not project:
        return {"error": "Project not found"}, 404
    uid, role = _actor()
    if role != "admin" and str(project["owner_id"]) != uid and str(user_id) != uid:
        return {"error": "Not allowed"}, 403
    if str(project["owner_id"]) == str(user_id):
        return {"error": "Cannot remove the project owner"}, 400
    res = get_db().projects.update_one(
        {"_id": project["_id"]},
        {"$pull": {"members": {"user_id": str(user_id)}}},
    )
    if res.matched_count == 0:
        return {"error": "Project not found"}, 404
    return {"project": serialize(find_project(pid))}, 200


@projects_bp.get("/<pid>/users")
@jwt_required()
def project_users(pid):
    """Directory of project members — used by assignee pickers and @mentions."""
    project = find_project(pid)
    if not project:
        return {"error": "Project not found"}, 404
    uid, role = _actor()
    if not can_view_project(project, uid, role):
        return {"error": "Not a member of this project"}, 403
    db = get_db()
    ids = [oid(project["owner_id"])] + [oid(m["user_id"]) for m in project.get("members", [])]
    users = db.users.find({"_id": {"$in": ids}}, {"password_hash": 0})
    return {"users": serialize(list(users))}, 200


# --- Labels ------------------------------------------------------------------

@projects_bp.get("/<pid>/labels")
@jwt_required()
def list_labels(pid):
    project = find_project(pid)
    if not project:
        return {"error": "Project not found"}, 404
    uid, role = _actor()
    if not can_view_project(project, uid, role):
        return {"error": "Not a member of this project"}, 403
    docs = list(get_db().labels.find({"project_id": str(project["_id"])}).sort("name", 1))
    return {"labels": serialize(docs)}, 200


@projects_bp.post("/<pid>/labels")
@jwt_required()
def create_label(pid):
    project = find_project(pid)
    if not project:
        return {"error": "Project not found"}, 404
    uid, role = _actor()
    if role != "admin" and str(project["owner_id"]) != uid:
        return {"error": "Only the owner or an admin can create labels"}, 403
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    colour = (data.get("colour") or "#64748b").strip()
    if not name:
        return {"error": "Label name is required"}, 400
    db = get_db()
    if db.labels.find_one({"project_id": str(project["_id"]), "name": name}):
        return {"error": "Label already exists"}, 409
    from datetime import datetime, timezone
    doc = {"project_id": str(project["_id"]), "name": name, "colour": colour,
           "created_at": datetime.now(timezone.utc)}
    res = db.labels.insert_one(doc)
    doc["_id"] = res.inserted_id
    return {"label": serialize(doc)}, 201


@projects_bp.delete("/<pid>/labels/<label_id>")
@jwt_required()
def delete_label(pid, label_id):
    project = find_project(pid)
    if not project:
        return {"error": "Project not found"}, 404
    uid, role = _actor()
    if role != "admin" and str(project["owner_id"]) != uid:
        return {"error": "Only the owner or an admin can delete labels"}, 403
    res = get_db().labels.delete_one({"_id": oid(label_id), "project_id": str(project["_id"])})
    if res.deleted_count == 0:
        return {"error": "Label not found"}, 404
    return {"message": "Deleted"}, 200
