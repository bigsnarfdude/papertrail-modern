"""
Flask application factory
"""
from flask import Flask, jsonify, render_template, send_from_directory
from flask_cors import CORS
import logging
import os

from app.config import settings


def create_app():
    """
    Create and configure Flask application

    Returns:
        Flask app instance
    """
    # Set template and static folders
    template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend', 'templates'))
    static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend', 'static'))

    app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if settings.DEBUG else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Enable CORS
    CORS(app, origins=settings.CORS_ORIGINS)

    # Register blueprints
    from app.api.events import events_bp
    from app.api.compliance import compliance_bp
    from app.api.stream import stream_bp

    app.register_blueprint(events_bp)
    app.register_blueprint(compliance_bp)
    app.register_blueprint(stream_bp)

    # Dashboard routes
    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/static/<path:path>")
    def send_static(path):
        return send_from_directory(static_dir, path)

    # API info endpoint
    @app.route("/api")
    def api_root():
        return jsonify(
            {
                "name": settings.APP_NAME,
                "version": settings.APP_VERSION,
                "status": "running",
                "endpoints": {
                    "events": f"{settings.API_PREFIX}/events",
                    "compliance": f"{settings.API_PREFIX}/compliance",
                    "stream": f"{settings.API_PREFIX}/stream",
                    "dashboard": "/",
                },
            }
        )

    # API info endpoint
    @app.route(f"{settings.API_PREFIX}")
    def api_info():
        return jsonify(
            {
                "name": settings.APP_NAME,
                "version": settings.APP_VERSION,
                "endpoints": {
                    "POST /events": "Submit single event",
                    "POST /events/batch": "Submit batch events",
                    "GET /events/health": "Health check",
                    "GET /compliance/distinct/<metric>": "Get distinct count",
                    "GET /compliance/activity/check": "Check user activity",
                    "GET /compliance/top/<metric>": "Get top K heavy hitters",
                    "GET /compliance/summary/<system>": "Get metrics summary",
                    "GET /stream": "Real-time event stream (SSE)",
                },
            }
        )

    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({"error": "Internal server error"}), 500

    return app
