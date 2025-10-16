"""
Compliance query API endpoints
"""
from flask import Blueprint, request, jsonify
from datetime import datetime
import logging

from app.models.events import DistinctCountResponse, ActivityCheckResponse, TopKResponse
from app.core.storage import RedisStorage
from app.core.processor import EventProcessor
from app.utils.time_windows import TimeWindow, TimeWindowBucketer

logger = logging.getLogger(__name__)

compliance_bp = Blueprint("compliance", __name__, url_prefix="/api/v1/compliance")

# Initialize storage and processor
storage = RedisStorage()
processor = EventProcessor(storage)
bucketer = TimeWindowBucketer()


@compliance_bp.route("/distinct/<metric>", methods=["GET"])
def get_distinct_count(metric: str):
    """
    Get distinct count for a metric

    Query params:
    - system: System name (required)
    - window: Time window (1h, 1d, 1w) (default: 1h)
    - timestamp: ISO timestamp (default: now)

    Example:
    GET /api/v1/compliance/distinct/users?system=production_db&window=1d

    Response:
    {
      "metric": "users",
      "system": "production_db",
      "window": "1d",
      "count": 1247,
      "accuracy": "±2%"
    }
    """
    try:
        # Parse query parameters
        system = request.args.get("system")
        if not system:
            return jsonify({"error": "system parameter is required"}), 400

        window_str = request.args.get("window", "1h")
        window = bucketer.parse_window_string(window_str)

        timestamp_str = request.args.get("timestamp")
        timestamp = (
            datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            if timestamp_str
            else datetime.utcnow()
        )

        # Query HyperLogLog
        count = storage.get_hll_cardinality(metric, system, window, timestamp)

        return (
            jsonify(
                DistinctCountResponse(
                    metric=metric,
                    system=system,
                    window=window_str,
                    count=count,
                    accuracy="±2%",
                ).model_dump()
            ),
            200,
        )

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Error querying distinct count: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@compliance_bp.route("/activity/check", methods=["GET"])
def check_activity():
    """
    Check if user accessed system (using Bloom filter)

    Query params:
    - user_id: User ID (required)
    - system: System name (required)
    - window: Time window (1d, 1w) (default: 1d)
    - timestamp: ISO timestamp (default: now)

    Example:
    GET /api/v1/compliance/activity/check?user_id=user123&system=prod&window=1d

    Response:
    {
      "user_id": "user123",
      "system": "prod",
      "window": "1d",
      "accessed": true,
      "probability": 0.99,
      "note": "This is a probabilistic result"
    }
    """
    try:
        # Parse query parameters
        user_id = request.args.get("user_id")
        system = request.args.get("system")

        if not user_id or not system:
            return jsonify({"error": "user_id and system parameters are required"}), 400

        window_str = request.args.get("window", "1d")
        window = bucketer.parse_window_string(window_str)

        timestamp_str = request.args.get("timestamp")
        timestamp = (
            datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            if timestamp_str
            else datetime.utcnow()
        )

        # Check Bloom filter
        value = f"{user_id}:{system}"
        accessed = storage.check_bloom("user_activity", system, value, timestamp, window)

        return (
            jsonify(
                ActivityCheckResponse(
                    user_id=user_id,
                    system=system,
                    window=window_str,
                    accessed=accessed,
                    probability=0.99 if accessed else 1.0,
                ).model_dump()
            ),
            200,
        )

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Error checking activity: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@compliance_bp.route("/top/<metric>", methods=["GET"])
def get_top_k(metric: str):
    """
    Get top K heavy hitters

    Query params:
    - system: System name (required)
    - k: Number of items to return (default: 10)
    - window: Time window (1h, 1d) (default: 1h)
    - timestamp: ISO timestamp (default: now)

    Example:
    GET /api/v1/compliance/top/active_users?system=prod&k=10&window=1h

    Response:
    {
      "metric": "active_users",
      "window": "1h",
      "items": [
        {"item": "user123", "count": 247},
        {"item": "user456", "count": 189}
      ]
    }
    """
    try:
        # Parse query parameters
        system = request.args.get("system")
        if not system:
            return jsonify({"error": "system parameter is required"}), 400

        k = int(request.args.get("k", 10))
        window_str = request.args.get("window", "1h")
        window = bucketer.parse_window_string(window_str)

        timestamp_str = request.args.get("timestamp")
        timestamp = (
            datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            if timestamp_str
            else datetime.utcnow()
        )

        # Query TopK
        items = storage.get_topk(metric, system, k, timestamp, window)

        return (
            jsonify(TopKResponse(metric=metric, window=window_str, items=items).model_dump()),
            200,
        )

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Error querying top K: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@compliance_bp.route("/summary/<system>", methods=["GET"])
def get_metrics_summary(system: str):
    """
    Get comprehensive metrics summary for a system

    Query params:
    - timestamp: ISO timestamp (default: now)

    Example:
    GET /api/v1/compliance/summary/production_db

    Response:
    {
      "system": "production_db",
      "timestamp": "2025-10-16T10:30:00",
      "hourly": {
        "unique_users": 247,
        "unique_sessions": 312,
        "top_users": [...]
      },
      "daily": {
        "unique_users": 1247,
        "unique_sessions": 1589
      }
    }
    """
    try:
        timestamp_str = request.args.get("timestamp")
        timestamp = (
            datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            if timestamp_str
            else datetime.utcnow()
        )

        summary = processor.get_metrics_summary(system, timestamp)
        return jsonify(summary), 200

    except Exception as e:
        logger.error(f"Error getting metrics summary: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@compliance_bp.route("/snapshot/<date>", methods=["GET"])
def get_compliance_snapshot(date: str):
    """
    Get compliance snapshot for specific date

    Example:
    GET /api/v1/compliance/snapshot/2025-10-16

    Response:
    {
      "date": "2025-10-16",
      "systems": {...},
      "metrics": {...}
    }
    """
    try:
        snapshot_date = datetime.fromisoformat(date)
        snapshot = storage.get_compliance_snapshot(snapshot_date)

        if snapshot is None:
            return jsonify({"error": "Snapshot not found"}), 404

        return jsonify(snapshot), 200

    except ValueError as e:
        return jsonify({"error": f"Invalid date format: {str(e)}"}), 400
    except Exception as e:
        logger.error(f"Error getting snapshot: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500
