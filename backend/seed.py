"""Seed script — creates demo users (admin/member/reporter), projects, labels
and issues with realistic activity. Safe to rerun: every record is upserted by
a natural key, so no duplicates are created.

Run locally:  uv run python seed.py
In Docker:    docker compose exec api python seed.py
"""
from datetime import datetime, timezone, timedelta

from app import create_app
from app.db import get_db
from app.utils.auth_utils import hash_password

DEMO_USERS = [
    {"username": "admin", "password": "admin123", "email": "admin@example.com",
     "display_name": "Ada Admin", "role": "admin", "avatar_color": "#8b5cf6"},
    {"username": "member", "password": "member123", "email": "member@example.com",
     "display_name": "Sam Member", "role": "member", "avatar_color": "#3b82f6"},
    {"username": "reporter", "password": "reporter123", "email": "rep@example.com",
     "display_name": "Rita Reporter", "role": "reporter", "avatar_color": "#ef4444"},
]

PROJECTS = [
    {"key": "WEB", "name": "Website Redesign", "description": "Marketing site refresh.",
     "owner": "admin"},
    {"key": "API", "name": "Platform API", "description": "Public REST API work.",
     "owner": "admin"},
]

LABELS = {
    "WEB": [("bug", "#ef4444"), ("frontend", "#3b82f6"), ("content", "#10b981")],
    "API": [("bug", "#ef4444"), ("backend", "#8b5cf6"), ("docs", "#f59e0b")],
}

# (project_key, title, type, priority, state, assignee, reporter, labels, days_from_now)
ISSUES = [
    ("WEB", "Homepage hero image broken on mobile", "bug", "High", "To Do",
     "member", "reporter", ["bug", "frontend"], -2),
    ("WEB", "Rewrite About page copy", "task", "Low", "Backlog",
     None, "reporter", ["content"], 5),
    ("WEB", "Add dark mode toggle", "story", "Medium", "In Progress",
     "member", "admin", ["frontend"], 7),
    ("WEB", "Publish Q3 blog post", "task", "Medium", "Done",
     "admin", "admin", ["content"], -10),
    ("API", "Rate limiter returns wrong status code", "bug", "Urgent", "In Review",
     "member", "reporter", ["bug", "backend"], 1),
    ("API", "Document pagination query params", "task", "Medium", "To Do",
     None, "admin", ["docs"], 3),
    ("API", "Support field selection in list endpoints", "story", "High", "Backlog",
     None, "admin", ["backend"], 14),
]


def now():
    return datetime.now(timezone.utc)


def seed():
    db = get_db()
    user_ids = {}

    for u in DEMO_USERS:
        existing = db.users.find_one({"username": u["username"]})
        doc = {k: v for k, v in u.items() if k != "password"}
        doc["created_at"] = existing.get("created_at", now()) if existing else now()
        if existing:
            # keep the stored hash stable on re-runs; set it only when creating
            doc["password_hash"] = existing["password_hash"]
            db.users.update_one({"_id": existing["_id"]}, {"$set": doc})
            user_ids[u["username"]] = str(existing["_id"])
        else:
            doc["password_hash"] = hash_password(u["password"])
            res = db.users.insert_one(doc)
            user_ids[u["username"]] = str(res.inserted_id)
            print(f"created user {u['username']} ({u['role']})")

    project_ids = {}
    for p in PROJECTS:
        owner_id = user_ids[p["owner"]]
        members = []
        for m in DEMO_USERS:
            if m["username"] != p["owner"]:
                prole = "reporter" if m["role"] == "reporter" else "member"
                members.append({"user_id": user_ids[m["username"]], "role": prole})
        existing = db.projects.find_one({"key": p["key"]})
        if existing:
            db.projects.update_one(
                {"_id": existing["_id"]},
                {"$set": {"name": p["name"], "description": p["description"],
                          "owner_id": owner_id, "members": members}})
            project_ids[p["key"]] = str(existing["_id"])
            next_num = existing.get("next_issue_num", 1)
        else:
            doc = {"key": p["key"], "name": p["name"], "description": p["description"],
                   "owner_id": owner_id, "members": members, "workflow": None,
                   "next_issue_num": 1, "created_at": now()}
            res = db.projects.insert_one(doc)
            project_ids[p["key"]] = str(res.inserted_id)
            next_num = 1
            print(f"created project {p['key']}")

        for name, colour in LABELS[p["key"]]:
            db.labels.update_one(
                {"project_id": project_ids[p["key"]], "name": name},
                {"$set": {"colour": colour, "created_at": now()}}, upsert=True)

    # Seed issues only once per project (natural key check keeps reruns safe).
    for (pkey, title, itype, prio, state, assignee, reporter, labels, ddelta) in ISSUES:
        pid = project_ids[pkey]
        if db.issues.find_one({"project_id": pid, "title": title}):
            continue
        proj = db.projects.find_one_and_update(
            {"_id": oid(pid)}, {"$inc": {"next_issue_num": 1}})
        num = proj["next_issue_num"]
        key = f"{pkey}-{num}"
        ts = now() + timedelta(days=ddelta)
        actor = user_ids[reporter]
        activity = [{
            "field": "created", "old_value": None, "new_value": key,
            "actor_id": actor, "actor_name": next(u["display_name"] for u in DEMO_USERS
                                                  if u["username"] == reporter),
            "timestamp": ts.isoformat(),
        }]
        if assignee:
            activity.append({
                "field": "assignee", "old_value": None,
                "new_value": next(u["display_name"] for u in DEMO_USERS
                                  if u["username"] == assignee),
                "actor_id": actor, "actor_name": "seed", "timestamp": ts.isoformat()})
        doc = {
            "project_id": pid, "key": key, "title": title,
            "description": f"Seeded demo issue for the {pkey} project.",
            "type": itype, "priority": prio, "state": state,
            "assignee_id": user_ids[assignee] if assignee else None,
            "reporter_id": actor, "labels": labels,
            "due_date": (ts + timedelta(days=5)).strftime("%Y-%m-%d"),
            "comments": [], "activity": activity,
            "created_at": ts, "updated_at": ts,
        }
        db.issues.insert_one(doc)
        print(f"created issue {key}: {title}")

    print("Seed complete. Demo logins:")
    for u in DEMO_USERS:
        print(f"  {u['username']} / {u['password']}  ({u['role']})")


def oid(s):
    from bson import ObjectId
    return ObjectId(s)


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        seed()
