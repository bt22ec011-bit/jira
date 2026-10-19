"""Issue CRUD, workflow transitions, comments/mentions, filters, activity feed.

Permission model (enforced server-side):
- Only project members (incl. owner/admin) can see issues in that project.
- Create: any project member or reporter.
- Edit fields (title/description/due date): assignee, reporter(own), owner, admin.
- Move state / assign: ONLY assignee, project owner, or global admin —
  a per-project reporter can never move or assign issues.
- Illegal transitions rejected with 422 by the configured state machine.
- Every change to state/assignee/priority/labels appends an immutable activity entry.
"""
from datetime import datetime, timezone

from flask import Blueprint, request, current_app
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from pymongo.errors import DuplicateKeyError

from app.db import get_db
from app.utils.helpers import (
    oid, serialize, find_project, get_membership, can_view_project, actor_name,
    enrich_issue_names,
)
from app.services.workflow import TransitionError, validate_transition, diff_activity

issues_bp = Blueprint("issues", __name__)


def _actor():
    claims = get_jwt()
    uid = str(get_jwt_identity())
    return uid, claims.get("role", "member"), actor_name(uid)


def _can_move(project, issue, uid, role, prole):
    if role == "admin":
        return True
    if str(project.get("owner_id")) == uid:
        return True
    if prole == "reporter":
        return False  # reporters may never move or assign
    return str(issue.get("assignee_id") or "") == uid


# --- List / search -------------------------------------------------------------

@issues_bp.get("")
@jwt_required()
def list_issues():
    """Filtered, paginated issue list across all projects visible to the user.

    Query params: project_id, state, assignee, label, priority, type, q,
                  sort (created_at|updated_at|key|priority), order (asc|desc),
                  page, per_page, mine (=assigned|reported).
    Filtering happens in MongoDB, not in React.
    """
    db = get_db()
    uid, role, _ = _actor()
    args = request.args

    # restrict to projects the caller belongs to
    if role == "admin":
        vis_projects = list(db.projects.find({}, {"_id": 1}))
    else:
        vis_projects = list(db.projects.find(
            {"$or": [{"owner_id": oid(uid)}, {"members.user_id": oid(uid)}]}, {"_id": 1}))
    vis_ids = [str(p["_id"]) for p in vis_projects]

    query = {"project_id": {"$in": vis_ids}}
    if args.get("project_id"):
        pid = str(args["project_id"])
        if pid not in vis_ids:
            return {"error": "You are not a member of this project"}, 403
        query["project_id"] = pid

    if args.get("state"):
        states = [s for s in args.getlist("state") if s in current_app.config["STATES"]]
        if states:
            query["state"] = {"$in": states}
    if args.get("priority"):
        query["priority"] = {"$in": args.getlist("priority")}
    if args.get("type"):
        query["type"] = {"$in": args.getlist("type")}
    if args.get("label"):
        query["labels"] = {"$in": args.getlist("label")}
    if args.get("assignee"):
        query["assignee_id"] = args["assignee"]
    if args.get("mine") in ("assigned", "reported"):
        field = "assignee_id" if args["mine"] == "assigned" else "reporter_id"
        query[field] = uid
    if args.get("q"):
        q = args["q"].strip()
        if q:
            safe = q.replace("'", "\\'")
            query["$or"] = [
                {"title": {"$regex": safe, "$options": "i"}},
                {"description": {"$regex": safe, "$options": "i"}},
            ]

    page = max(int(args.get("page", 1)), 1)
    per_page = min(max(int(args.get("per_page", 50)), 1), 100)
    sort_field = args.get("sort", "updated_at")
    if sort_field not in ("created_at", "updated_at", "key", "priority", "state"):
        sort_field = "updated_at"
    order = -1 if args.get("order", "desc").lower() == "desc" else 1

    total = db.issues.count_documents(query)
    docs = list(db.issues.find(query)
                .sort(sort_field, order)
                .skip((page - 1) * per_page)
                .limit(per_page))
    return {
        "items": enrich_issue_names(serialize(docs)),
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max((total + per_page - 1) // per_page, 1),
    }, 200


@issues_bp.get("/counts")
@jwt_required()
def issue_counts():
    """Issue counts grouped by state (project health strip) — aggregation in DB."""
    db = get_db()
    uid, role, _ = _actor()
    pid = request.args.get("project_id")
    if pid:
        project = find_project(pid)
        if not project:
            return {"error": "Project not found"}, 404
        if not can_view_project(project, uid, role):
            return {"error": "Not a member of this project"}, 403
        match = {"project_id": str(project["_id"])}
    else:
        if role == "admin":
            vis_ids = [str(p["_id"]) for p in db.projects.find({}, {"_id": 1})]
        else:
            vis_ids = [str(p["_id"]) for p in db.projects.find(
                {"$or": [{"owner_id": oid(uid)}, {"members.user_id": oid(uid)}]}, {"_id": 1})]
        match = {"project_id": {"$in": vis_ids}}

    pipeline = [
        {"$match": match},
        {"$group": {"_id": "$state", "count": {"$sum": 1}}},
    ]
    grouped = {r["_id"]: r["count"] for r in db.issues.aggregate(pipeline)}
    counts = {s: grouped.get(s, 0) for s in current_app.config["STATES"]}
    return {"counts": counts, "total": sum(counts.values())}, 200


@issues_bp.get("/<iid>")
@jwt_required()
def get_issue(iid):
    db = get_db()
    issue = db.issues.find_one({"_id": oid(iid)})
    if not issue:
        return {"error": "Issue not found"}, 404
    uid, role, _ = _actor()
    project = find_project(issue["project_id"])
    if not project or not can_view_project(project, uid, role):
        return {"error": "You are not a member of this project"}, 403
    out = enrich_issue_names([serialize(issue)])[0]
    out["my_role"] = (get_membership(project, uid) or {}).get("role") or ("admin" if role == "admin" else None)
    return {"issue": out}, 200


# --- Create --------------------------------------------------------------------

@issues_bp.post("")
@jwt_required()
def create_issue():
    db = get_db()
    uid, role, _ = _actor()
    data = request.get_json(silent=True) or {}

    project = find_project(data.get("project_id"))
    if not project:
        return {"error": "Project not found"}, 404
    membership = get_membership(project, uid)
    if role != "admin" and membership is None:
        return {"error": "You are not a member of this project"}, 403

    title = (data.get("title") or "").strip()
    if not title:
        return {"error": "Title is required"}, 400
    itype = data.get("type", "task")
    if itype not in current_app.config["ISSUE_TYPES"]:
        return {"error": f"type must be one of {current_app.config['ISSUE_TYPES']}"}, 400
    priority = data.get("priority", "Medium")
    if priority not in current_app.config["PRIORITIES"]:
        return {"error": f"priority must be one of {current_app.config['PRIORITIES']}"}, 400
    state = data.get("state", "Backlog")
    if state not in current_app.config["STATES"]:
        return {"error": f"state must be one of {current_app.config['STATES']}"}, 400

    labels = data.get("labels") or []
    if not isinstance(labels, list):
        return {"error": "labels must be a list"}, 400
    existing = {l["name"] for l in db.labels.find({"project_id": str(project["_id"])})}
    bad = [l for l in labels if l not in existing]
    if bad:
        return {"error": f"Unknown labels: {', '.join(bad)}"}, 400

    assignee_id = data.get("assignee_id") or None
    if assignee_id:
        # assigning at creation requires move permission (not a reporter)
        if not _can_move(project, {}, uid, role, (membership or {}).get("role")):
            return {"error": "Reporters cannot assign issues"}, 403
        if not db.users.find_one({"_id": oid(assignee_id)}):
            return {"error": "Assignee not found"}, 400

    due_date = data.get("due_date") or None

    # atomic counter for issue numbers -> PROJ-14 style keys
    proj = db.projects.find_one_and_update(
        {"_id": project["_id"]}, {"$inc": {"next_issue_num": 1}},
        return_document=__import__("pymongo").ReturnDocument.AFTER)
    key = f"{proj['key']}-{proj['next_issue_num']}"

    now = datetime.now(timezone.utc)
    doc = {
        "project_id": str(project["_id"]),
        "key": key,
        "title": title,
        "description": (data.get("description") or "").strip(),
        "type": itype,
        "priority": priority,
        "state": state,
        "assignee_id": assignee_id,
        "reporter_id": uid,
        "labels": labels,
        "due_date": due_date,
        "comments": [],
        "activity": [{
            "field": "created", "old_value": None, "new_value": key,
            "actor_id": uid, "actor_name": actor_name(uid),
            "timestamp": now.isoformat(),
        }],
        "created_at": now,
        "updated_at": now,
    }
    try:
        res = db.issues.insert_one(doc)
    except DuplicateKeyError:
        return {"error": "Issue key collision, please retry"}, 409
    doc["_id"] = res.inserted_id
    return {"issue": enrich_issue_names([serialize(doc)])[0]}, 201


# --- Update (fields; state handled via /transition) ------------------------------

@issues_bp.put("/<iid>")
@jwt_required()
def update_issue(iid):
    db = get_db()
    uid, role, actor_name = _actor()
    issue = db.issues.find_one({"_id": oid(iid)})
    if not issue:
        return {"error": "Issue not found"}, 404
    project = find_project(issue["project_id"])
    if not project or not can_view_project(project, uid, role):
        return {"error": "You are not a member of this project"}, 403

    membership = get_membership(project, uid)
    prole = (membership or {}).get("role")
    is_assignee = str(issue.get("assignee_id") or "") == uid
    is_reporter_of_issue = str(issue.get("reporter_id") or "") == uid
    can_manage = _can_move(project, issue, uid, role, prole)  # owner/admin/assignee

    data = request.get_json(silent=True) or {}
    changes = {}

    # plain text fields — editable by anyone who can touch the issue at all
    if not (can_manage or is_reporter_of_issue):
        return {"error": "You cannot edit this issue"}, 403

    if "title" in data:
        t = (data.get("title") or "").strip()
        if not t:
            return {"error": "Title cannot be empty"}, 400
        changes["title"] = t
    if "description" in data:
        changes["description"] = (data.get("description") or "").strip()
    if "due_date" in data:
        changes["due_date"] = data.get("due_date") or None
    if "type" in data:
        if data["type"] not in current_app.config["ISSUE_TYPES"]:
            return {"error": "Invalid type"}, 400
        changes["type"] = data["type"]

    # tracked fields require manage permission (never granted to reporters)
    for field, cfg in (("priority", "PRIORITIES"), ("state", "STATES")):
        if field in data:
            if not can_manage:
                return {"error": "Only the assignee, project owner or an admin "
                                 "may change priority or move issues"}, 403
            val = data[field]
            allowed = current_app.config[cfg]
            if field == "state":
                try:
                    validate_transition(issue["state"], val)
                except TransitionError as e:
                    return {"error": str(e)}, 422
            elif val not in allowed:
                return {"error": f"Invalid {field}"}, 400
            changes[field] = val

    if "assignee_id" in data:
        if not can_manage:
            return {"error": "Reporters cannot assign issues"}, 403
        new_a = data["assignee_id"] or None
        if new_a and not db.users.find_one({"_id": oid(new_a)}):
            return {"error": "Assignee not found"}, 400
        changes["assignee_id"] = new_a

    if "labels" in data:
        if not can_manage:
            return {"error": "Reporters cannot change labels"}, 403
        labels = data.get("labels") or []
        if not isinstance(labels, list):
            return {"error": "labels must be a list"}, 400
        existing = {l["name"] for l in db.labels.find({"project_id": str(project["_id"])})}
        bad = [l for l in labels if l not in existing]
        if bad:
            return {"error": f"Unknown labels: {', '.join(bad)}"}, 400
        changes["labels"] = labels

    if not changes:
        return {"error": "No valid fields to update"}, 400

    entries = diff_activity(issue, changes, uid, actor_name or uid)
    updates = dict(changes)
    updates["updated_at"] = datetime.now(timezone.utc)
    ops = {"$set": updates}
    if entries:
        ops["$push"] = {"activity": {"$each": entries}}

    db.issues.update_one({"_id": issue["_id"]}, ops)
    return {"issue": enrich_issue_names([serialize(db.issues.find_one({"_id": issue["_id"]}))])[0]}, 200


# --- Dedicated transition endpoint (used by Kanban drag & drop) -------------------

@issues_bp.post("/<iid>/transition")
@jwt_required()
def transition_issue(iid):
    db = get_db()
    uid, role, actor_name = _actor()
    issue = db.issues.find_one({"_id": oid(iid)})
    if not issue:
        return {"error": "Issue not found"}, 404
    project = find_project(issue["project_id"])
    if not project or not can_view_project(project, uid, role):
        return {"error": "You are not a member of this project"}, 403

    membership = get_membership(project, uid)
    prole = (membership or {}).get("role")
    if not _can_move(project, issue, uid, role, prole):
        return {"error": "Only the assignee, project owner or an admin may move this issue"}, 403

    data = request.get_json(silent=True) or {}
    to_state = data.get("to_state") or data.get("state")
    if not to_state:
        return {"error": "to_state is required"}, 400

    try:
        validate_transition(issue["state"], to_state)
    except TransitionError as e:
        return {"error": str(e)}, 422

    entries = diff_activity(issue, {"state": to_state}, uid, actor_name or uid)
    db.issues.update_one(
        {"_id": issue["_id"]},
        {"$set": {"state": to_state, "updated_at": datetime.now(timezone.utc)},
         "$push": {"activity": {"$each": entries}}},
    )
    return {"issue": enrich_issue_names([serialize(db.issues.find_one({"_id": issue["_id"]}))])[0]}, 200


# --- Comments with @mentions -------------------------------------------------------

@issues_bp.post("/<iid>/comments")
@jwt_required()
def add_comment(iid):
    db = get_db()
    uid, role, actor_name = _actor()
    issue = db.issues.find_one({"_id": oid(iid)})
    if not issue:
        return {"error": "Issue not found"}, 404
    project = find_project(issue["project_id"])
    if not project or not can_view_project(project, uid, role):
        return {"error": "You are not a member of this project"}, 403

    data = request.get_json(silent=True) or {}
    body = (data.get("body") or "").strip()
    if not body:
        return {"error": "Comment body is required"}, 400

    # parse @mentions and validate each mentioned user belongs to the project
    import re
    tokens = set(re.findall(r"@([A-Za-z0-9_]+)", body))
    member_names = set()
    ids = [oid(project["owner_id"])] + [oid(m["user_id"]) for m in project.get("members", [])]
    users = list(db.users.find({"_id": {"$in": ids}}, {"username": 1, "display_name": 1}))
    by_username = {u["username"]: u for u in users}
    member_names.update(by_username.keys())

    mentions = []
    invalid = []
    for t in tokens:
        tl = t.lower()
        match = next((un for un in member_names if un.lower() == tl), None)
        if match:
            mentions.append({"user_id": str(by_username[match]["_id"]),
                             "username": match})
        else:
            invalid.append(t)
    if invalid:
        return {"error": f"Mentioned users are not project members: {', '.join(invalid)}"}, 400

    comment = {
        "author_id": uid,
        "author_name": actor_name or uid,
        "body": body,
        "mentions": mentions,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    db.issues.update_one(
        {"_id": issue["_id"]},
        {"$push": {"comments": comment},
         "$set": {"updated_at": datetime.now(timezone.utc)}},
    )
    return {"comment": serialize(comment),
            "issue": enrich_issue_names([serialize(db.issues.find_one({"_id": issue["_id"]}))])[0]}, 201


# --- Activity feed (append-only; no edit/delete endpoints exist) --------------------

@issues_bp.get("/<iid>/activity")
@jwt_required()
def issue_activity(iid):
    db = get_db()
    issue = db.issues.find_one({"_id": oid(iid)})
    if not issue:
        return {"error": "Issue not found"}, 404
    uid, role, _ = _actor()
    project = find_project(issue["project_id"])
    if not project or not can_view_project(project, uid, role):
        return {"error": "You are not a member of this project"}, 403
    acts = sorted(issue.get("activity", []), key=lambda a: a["timestamp"], reverse=True)
    return {"activity": serialize(acts)}, 200


@issues_bp.get("/activity")
@jwt_required()
def project_activity_feed():
    """Per-project activity feed: newest entries across issues, via aggregation."""
    db = get_db()
    uid, role, _ = _actor()
    pid = request.args.get("project_id")
    if not pid:
        return {"error": "project_id query param is required"}, 400
    project = find_project(pid)
    if not project:
        return {"error": "Project not found"}, 404
    if not can_view_project(project, uid, role):
        return {"error": "You are not a member of this project"}, 403

    limit = min(max(int(request.args.get("limit", 30)), 1), 100)
    pipeline = [
        {"$match": {"project_id": str(project["_id"])}},
        {"$unwind": "$activity"},
        {"$sort": {"activity.timestamp": -1}},
        {"$limit": limit},
        {"$project": {
            "activity": 1, "key": 1, "title": 1,
            "issue_id": {"$toString": "$_id"},
        }},
    ]
    feed = list(db.issues.aggregate(pipeline))
    return {"feed": serialize(feed)}, 200
