"""
main.py — Flask application factory for InfraGraph backend.

Usage:
    FLASK_APP=app.main:create_app flask run
    python -m flask --app app.main:create_app run
"""

from flask import Flask
from flask_cors import CORS

from .routes.parse import parse_bp
from .routes.graph import graph_bp


def create_app() -> Flask:
    app = Flask(__name__)

    # Allow requests from both Docker frontend (3000) and Vite dev server (5173)
    CORS(app, origins=["http://localhost:3000", "http://localhost:5173"])

    # Register blueprints
    app.register_blueprint(parse_bp, url_prefix="/parse")
    app.register_blueprint(graph_bp, url_prefix="/graph")

    # Health check — used by Docker Compose healthcheck and load balancers
    @app.route("/health")
    def health():
        return {"status": "ok"}

    # Global error handlers
    @app.errorhandler(400)
    def bad_request(exc):
        return {"error": str(exc)}, 400

    @app.errorhandler(404)
    def not_found(exc):
        return {"error": "Not found"}, 404

    @app.errorhandler(405)
    def method_not_allowed(exc):
        return {"error": "Method not allowed"}, 405

    @app.errorhandler(500)
    def server_error(exc):
        return {"error": "Internal server error"}, 500

    return app
