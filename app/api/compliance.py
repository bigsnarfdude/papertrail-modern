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


# =====================
# NEW! T-Digest Percentile Endpoints
# =====================

@compliance_bp.route("/percentiles/<metric>", methods=["GET"])
def get_percentiles(metric: str):
    """
    Get percentile statistics for a metric (NEW algesnake T-Digest feature!)

    Query params:
    - system: System name (required)
    - percentiles: Comma-separated list (e.g., "50,95,99") (default: "50,95,99")
    - window: Time window (1h, 1d) (default: 1h)
    - timestamp: ISO timestamp (default: now)

    Example:
    GET /api/v1/compliance/percentiles/api_latency?system=prod&percentiles=50,95,99&window=1h

    Response:
    {
      "metric": "api_latency",
      "system": "prod",
      "window": "1h",
      "percentiles": {
        "p50": 45.2,
        "p95": 189.7,
        "p99": 512.3
      },
      "unit": "milliseconds",
      "timestamp": "2025-10-23T10:30:00"
    }
    """
    try:
        # Parse query parameters
        system = request.args.get("system")
        if not system:
            return jsonify({"error": "system parameter is required"}), 400

        percentiles_str = request.args.get("percentiles", "50,95,99")
        percentiles = [float(p.strip()) for p in percentiles_str.split(",")]

        window_str = request.args.get("window", "1h")
        window = bucketer.parse_window_string(window_str)

        timestamp_str = request.args.get("timestamp")
        timestamp = (
            datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            if timestamp_str
            else datetime.utcnow()
        )

        # Query T-Digest
        results = storage.get_tdigest_percentiles(metric, system, percentiles, timestamp, window)

        # Format response
        percentile_dict = {f"p{int(p)}": v for p, v in results.items()}

        return jsonify({
            "metric": metric,
            "system": system,
            "window": window_str,
            "percentiles": percentile_dict,
            "unit": "milliseconds",  # configurable per metric
            "timestamp": timestamp.isoformat()
        }), 200

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Error querying percentiles: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@compliance_bp.route("/sla/check", methods=["GET"])
def check_sla():
    """
    Check SLA compliance using T-Digest percentiles (NEW!)

    Query params:
    - metric: Metric name (e.g., "api_latency") (required)
    - system: System name (required)
    - percentile: Percentile to check (e.g., 95 for p95) (default: 95)
    - threshold: Maximum acceptable value (required)
    - window: Time window (1h, 1d) (default: 1h)
    - timestamp: ISO timestamp (default: now)

    Example:
    GET /api/v1/compliance/sla/check?metric=api_latency&system=prod&percentile=95&threshold=200&window=1h

    Response:
    {
      "metric": "api_latency",
      "system": "prod",
      "percentile": 95,
      "value": 189.7,
      "threshold": 200,
      "status": "PASS",
      "margin": 10.3,
      "window": "1h",
      "timestamp": "2025-10-23T10:30:00"
    }
    """
    try:
        # Parse query parameters
        metric = request.args.get("metric")
        system = request.args.get("system")
        threshold_str = request.args.get("threshold")

        if not metric or not system or not threshold_str:
            return jsonify({"error": "metric, system, and threshold parameters are required"}), 400

        percentile = float(request.args.get("percentile", "95"))
        threshold = float(threshold_str)

        window_str = request.args.get("window", "1h")
        window = bucketer.parse_window_string(window_str)

        timestamp_str = request.args.get("timestamp")
        timestamp = (
            datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            if timestamp_str
            else datetime.utcnow()
        )

        # Query T-Digest
        value = storage.get_tdigest_percentile(metric, system, percentile, timestamp, window)

        if value is None:
            return jsonify({"error": "No data available for specified metric/system"}), 404

        # Check SLA
        status = "PASS" if value < threshold else "FAIL"
        margin = threshold - value

        return jsonify({
            "metric": metric,
            "system": system,
            "percentile": int(percentile),
            "value": round(value, 2),
            "threshold": threshold,
            "status": status,
            "margin": round(margin, 2),
            "window": window_str,
            "timestamp": timestamp.isoformat()
        }), 200

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Error checking SLA: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@compliance_bp.route("/latency/summary/<system>", methods=["GET"])
def get_latency_summary(system: str):
    """
    Get comprehensive latency summary for a system (NEW!)

    Query params:
    - metric: Metric name (default: "api_latency")
    - window: Time window (1h, 1d) (default: 1h)
    - timestamp: ISO timestamp (default: now)

    Example:
    GET /api/v1/compliance/latency/summary/prod?window=1h

    Response:
    {
      "system": "prod",
      "metric": "api_latency",
      "window": "1h",
      "percentiles": {
        "p50": 45.2,
        "p90": 125.8,
        "p95": 189.7,
        "p99": 512.3,
        "p999": 1247.6
      },
      "sla_status": {
        "p95_under_200ms": "PASS",
        "p99_under_500ms": "FAIL"
      },
      "timestamp": "2025-10-23T10:30:00"
    }
    """
    try:
        metric = request.args.get("metric", "api_latency")
        window_str = request.args.get("window", "1h")
        window = bucketer.parse_window_string(window_str)

        timestamp_str = request.args.get("timestamp")
        timestamp = (
            datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            if timestamp_str
            else datetime.utcnow()
        )

        # Query percentiles
        percentiles = [50, 90, 95, 99, 99.9]
        results = storage.get_tdigest_percentiles(metric, system, percentiles, timestamp, window)

        # Format percentiles
        percentile_dict = {}
        for p, v in results.items():
            if v is not None:
                key = f"p{int(p)}" if p == int(p) else f"p{p}".replace(".", "")
                percentile_dict[key] = round(v, 2)

        # Check common SLA thresholds
        sla_status = {}
        p95 = results.get(95)
        p99 = results.get(99)

        if p95 is not None:
            sla_status["p95_under_200ms"] = "PASS" if p95 < 200 else "FAIL"
        if p99 is not None:
            sla_status["p99_under_500ms"] = "PASS" if p99 < 500 else "FAIL"

        return jsonify({
            "system": system,
            "metric": metric,
            "window": window_str,
            "percentiles": percentile_dict,
            "sla_status": sla_status,
            "timestamp": timestamp.isoformat()
        }), 200

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Error getting latency summary: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500
