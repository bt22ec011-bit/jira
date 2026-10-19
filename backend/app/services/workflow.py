"""Workflow state machine and immutable activity trail (core business logic)."""
from datetime import datetime, timezone

from flask import current_app


class TransitionError(Exception):
    """Raised when a state transition is not allowed -> HTTP 422."""


def can_transition(current_state: str, new_state: str) -> bool:
    allowed = current_app.config["ALLOWED_TRANSITIONS"].get(current_state, [])
    return new_state in allowed


def validate_transition(current_state: str, new_state: str):
    if current_state == new_state:
        raise TransitionError(f"Issue is already in state '{current_state}'")
    if new_state not in current_app.config["STATES"]:
        raise TransitionError(f"Unknown state '{new_state}'")
    if not can_transition(current_state, new_state):
        raise TransitionError(
            f"Illegal transition: {current_state} -> {new_state}. "
            f"Allowed from '{current_state}': "
            f"{', '.join(current_app.config['ALLOWED_TRANSITIONS'].get(current_state, [])) or 'none'}"
        )


def make_activity_entry(field, old_value, new_value, actor_id, actor_name):
    """Activity entries are append-only: field, old value, new value, actor, timestamp."""
    return {
        "field": field,
        "old_value": old_value,
        "new_value": new_value,
        "actor_id": str(actor_id),
        "actor_name": actor_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def diff_activity(issue, changes, actor_id, actor_name):
    """Build activity entries for tracked fields: state, assignee, priority, labels."""
    entries = []

    def add(field, old, new):
        entries.append(make_activity_entry(field, old, new, actor_id, actor_name))

    if "state" in changes and changes["state"] != issue.get("state"):
        add("state", issue.get("state"), changes["state"])
    if "assignee_id" in changes:
        old = issue.get("assignee_id")
        new = changes["assignee_id"]
        if str(old or "") != str(new or ""):
            add("assignee", _name_of(old), _name_of(new))
    if "priority" in changes and changes["priority"] != issue.get("priority"):
        add("priority", issue.get("priority"), changes["priority"])
    if "labels" in changes:
        old_labels = sorted(issue.get("labels", []))
        new_labels = sorted(changes["labels"])
        if old_labels != new_labels:
            add("labels", ", ".join(old_labels) or None, ", ".join(new_labels) or None)
    return entries


def _name_of(user_id):
    if not user_id:
        return None
    from app.db import get_db
    from app.utils.helpers import oid
    u = get_db().users.find_one({"_id": oid(user_id)}, {"display_name": 1})
    return (u.get("display_name") if u else None) or str(user_id)
