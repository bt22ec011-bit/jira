"""Shared helpers: JSON serialisation of Mongo docs and project access checks."""
from bson import ObjectId
from bson.errors import InvalidId

from app.db import get_db


def actor_name(user_id):
    """Resolve a display name for activity entries (never leaks raw ids)."""
    db = get_db()
    u = db.users.find_one({"_id": oid(user_id)}, {"display_name": 1, "username": 1})
    if u:
        return u.get("display_name") or u.get("username")
    return str(user_id)


def oid(value):
    """Return ObjectId for a valid hex id, else None (never raises)."""
    try:
        return ObjectId(str(value))
    except (InvalidId, TypeError):
        return None


def to_str_id(doc):
    if doc and "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    return doc


def serialize(doc):
    """Recursively convert ObjectIds/datetimes for JSON responses."""
    if isinstance(doc, dict):
        out = {}
        for k, v in doc.items():
            if k == "_id":
                out["id"] = str(v)
            elif isinstance(v, ObjectId):
                out[k] = str(v)
            elif hasattr(v, "isoformat"):  # datetime
                out[k] = v.isoformat()
            else:
                out[k] = serialize(v)
        return out
    if isinstance(doc, list):
        return [serialize(x) for x in doc]
    return doc


def find_project(project_id):
    db = get_db()
    pid = oid(project_id)
    if pid is None:
        return None
    return db.projects.find_one({"_id": pid})


def get_membership(project, user_id):
    """Return the member entry for user_id inside project, or None.

    The owner is always an implicit 'owner' member."""
    if not project:
        return None
    if str(project.get("owner_id")) == str(user_id):
        return {"user_id": str(project["owner_id"]), "role": "owner"}
    for m in project.get("members", []):
        if str(m.get("user_id")) == str(user_id):
            return m
    return None


def can_view_project(project, user_id, role):
    return role == "admin" or get_membership(project, user_id) is not None


def can_edit_issue(issue, project, user_id, role):
    """Assignee, reporter (own issue), project owner or admin may edit fields."""
    if role == "admin":
        return True
    if str(project.get("owner_id")) == str(user_id):
        return True
    uid = str(user_id)
    if str(issue.get("assignee_id") or "") == uid:
        return True
    if str(issue.get("reporter_id") or "") == uid:
        # reporters may edit their own issue's description/title but never
        # move or assign it — enforced separately in update_issue
        return True
    return False


def username_of(user_id):
    if not user_id:
        return None
    db = get_db()
    u = db.users.find_one({"_id": oid(user_id)}, {"display_name": 1, "username": 1})
    if u:
        return u.get("display_name") or u.get("username")
    return None


def enrich_issue_names(docs):
    """Attach assignee_name / reporter_name to serialized issue docs (one query)."""
    ids = set()
    for d in docs:
        for f in ("assignee_id", "reporter_id"):
            if d.get(f):
                ids.add(str(d[f]))
    if not ids:
        return docs
    db = get_db()
    from bson import ObjectId as _OID
    try:
        users = {str(u["_id"]): (u.get("display_name") or u.get("username"))
                 for u in db.users.find({"_id": {"$in": [_OID(i) for i in ids]}},
                                        {"display_name": 1, "username": 1})}
    except Exception:
        return docs
    for d in docs:
        d["assignee_name"] = users.get(str(d.get("assignee_id"))) if d.get("assignee_id") else None
        d["reporter_name"] = users.get(str(d.get("reporter_id"))) if d.get("reporter_id") else None
    return docs

