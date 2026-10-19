"""MongoDB connection setup using PyMongo directly (no ODM)."""
from pymongo import MongoClient, ASCENDING, TEXT

_client = None
_db = None


def init_db(app):
    global _client, _db
    _client = MongoClient(app.config["MONGO_URI"], serverSelectionTimeoutMS=5000)
    _db = _client[app.config["MONGO_DB"]]
    ensure_indexes(_db)


def get_db():
    if _db is None:
        raise RuntimeError("Database not initialised")
    return _db


def close_db(_exc=None):
    """No-op: MongoClient pools connections and is reused across requests.

    Closing it per-request would break subsequent ones ("Cannot use MongoClient
    after close"). The process owns the client's lifetime."""
    return


def ensure_indexes(db):
    """Sensible indexes for membership, issue state, assignee, key and search."""
    db.users.create_index("username", unique=True)
    db.projects.create_index("key", unique=True)
    db.projects.create_index([("members.user_id", ASCENDING)])
    db.projects.create_index("owner_id")
    # key is unique per project; issues.key carries the full "PROJ-14" string
    db.issues.create_index([("project_id", ASCENDING), ("key", ASCENDING)], unique=True)
    db.issues.create_index([("project_id", ASCENDING), ("state", ASCENDING)])
    db.issues.create_index([("assignee_id", ASCENDING), ("project_id", ASCENDING)])
    db.issues.create_index([("reporter_id", ASCENDING)])
    # Full-text search over title + description (basic regex search also works
    # without this index; text index powers /projects/<id>/activity style queries)
    try:
        db.issues.create_index([("title", TEXT), ("description", TEXT)])
    except Exception:
        pass  # text index conflicts with other index types on some setups
    db.labels.create_index([("project_id", ASCENDING), ("name", ASCENDING)], unique=True)
    db.token_blocklist.create_index("jti", unique=True)
    db.token_blocklist.create_index("exp")  # for TTL-style cleanup
