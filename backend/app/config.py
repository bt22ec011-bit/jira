import os


class Config:
    # --- MongoDB -----------------------------------------------------------
    MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB = os.environ.get("MONGO_DB", "issue_tracker")

    # --- JWT ---------------------------------------------------------------
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-secret-change-me")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES = int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRES", 900))     # 15 min
    JWT_REFRESH_TOKEN_EXPIRES = int(os.environ.get("JWT_REFRESH_TOKEN_EXPIRES", 604800))  # 7 days

    # --- Workflow state machine ---------------------------------------------
    # The five Kanban states, in board order.
    STATES = ["Backlog", "To Do", "In Progress", "In Review", "Done"]

    # Allowed transitions declared in configuration (core requirement).
    # An illegal jump such as Backlog -> Done is rejected with 422.
    ALLOWED_TRANSITIONS = {
        "Backlog": ["To Do"],
        "To Do": ["Backlog", "In Progress"],
        "In Progress": ["To Do", "In Review"],
        "In Review": ["In Progress", "Done"],
        "Done": ["In Review"],
    }

    PRIORITIES = ["Low", "Medium", "High", "Urgent"]
    ISSUE_TYPES = ["bug", "task", "story"]
    PROJECT_ROLES = ["member", "reporter"]      # per-project role for members[]
    GLOBAL_ROLES = ["admin", "member", "reporter"]  # users.role claim


def get_config():
    return Config
