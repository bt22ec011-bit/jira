"""Flask application factory."""
from dotenv import load_dotenv

load_dotenv()  # read backend/.env before config import pulls os.environ

from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from werkzeug.exceptions import HTTPException

from app.config import get_config
from app.db import init_db, close_db


def create_app(config_overrides=None):
    app = Flask(__name__)
    cfg = get_config()
    app.config.from_object(cfg)
    if config_overrides:
        app.config.update(config_overrides)

    CORS(app, resources={r"/api/*": {"origins": "*"}})
    JWTManager(app)  # logout invalidation is enforced via the JTI blocklist

    init_db(app)
    app.teardown_appcontext(close_db)

    from app.routes.auth_routes import auth_bp
    from app.routes.project_routes import projects_bp
    from app.routes.issue_routes import issues_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(projects_bp, url_prefix="/api/projects")
    app.register_blueprint(issues_bp, url_prefix="/api/issues")

    @app.get("/api/health")
    def health():
        return {"status": "ok"}, 200

    @app.get("/")
    def root():
        return jsonify({"name": "Issue Tracker API", "docs": "/api/health"}), 200

    # --- Error handling: consistent JSON, no stack traces leaked ---------------
    from pymongo.errors import PyMongoError

    @app.errorhandler(HTTPException)
    def handle_http_exc(e):
        return {"error": e.description}, e.code

    @app.errorhandler(PyMongoError)
    def handle_mongo_exc(e):
        app.logger.exception("MongoDB error")
        return {"error": "Database error"}, 500

    @app.errorhandler(Exception)
    def handle_unexpected(e):
        app.logger.exception("Unexpected error")
        return {"error": "Internal server error"}, 500

    # JWT extended errors -> JSON too
    return app
