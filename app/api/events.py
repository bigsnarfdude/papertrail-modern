"""
Event ingestion API endpoints
"""
from flask import Blueprint, request, jsonify
from datetime import datetime
import uuid
import logging

from app.models.events import Event, BatchEventRequest, EventResponse
from app.core.processor import EventProcessor
from app.core.storage import RedisStorage

logger = logging.getLogger(__name__)

events_bp = Blueprint("events", __name__, url_prefix="/api/v1/events")

# Initialize storage and processor
storage = RedisStorage()
processor = EventProcessor(storage)


@events_bp.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    redis_ok = storage.ping()
    return jsonify({"status": "healthy" if redis_ok else "unhealthy", "redis": redis_ok}), (
        200 if redis_ok else 503
    )


@events_bp.route("", methods=["POST"])
def submit_event():
    """
    Submit a single event

    Request Body:
    {
      "event_type": "user_login",
      "user_id": "user123",
      "system": "production_db",
      "timestamp": "2025-10-16T10:30:00Z",
      "metadata": {"ip": "192.168.1.1"}
    }

    Response:
    {
      "success": true,
      "event_id": "uuid",
      "message": "Event processed successfully"
    }
    """
    try:
        data = request.get_json()

        # Validate and parse event
        event = Event(**data)

        # Process event
        processor.process_event(event)

        # Return success
        return (
            jsonify(
                EventResponse(
                    success=True,
                    event_id=str(uuid.uuid4()),
                    message="Event processed successfully",
                ).model_dump()
            ),
            201,
        )

    except ValueError as e:
        logger.warning(f"Invalid event data: {e}")
        return (
            jsonify(
                EventResponse(
                    success=False, message=f"Invalid event data: {str(e)}"
                ).model_dump()
            ),
            400,
        )
    except Exception as e:
        logger.error(f"Error processing event: {e}", exc_info=True)
        return (
            jsonify(
                EventResponse(
                    success=False, message="Internal server error"
                ).model_dump()
            ),
            500,
        )


@events_bp.route("/batch", methods=["POST"])
def submit_batch():
    """
    Submit multiple events in batch

    Request Body:
    {
      "events": [
        {"event_type": "user_login", ...},
        {"event_type": "api_access", ...}
      ]
    }

    Response:
    {
      "success": true,
      "processed": 10,
      "total": 10,
      "message": "Batch processed successfully"
    }
    """
    try:
        data = request.get_json()

        # Validate batch request
        batch = BatchEventRequest(**data)

        # Process events
        processed = processor.process_batch(batch.events)

        return (
            jsonify(
                {
                    "success": True,
                    "processed": processed,
                    "total": len(batch.events),
                    "message": f"Processed {processed}/{len(batch.events)} events",
                }
            ),
            201,
        )

    except ValueError as e:
        logger.warning(f"Invalid batch data: {e}")
        return jsonify({"success": False, "message": f"Invalid batch data: {str(e)}"}), 400
    except Exception as e:
        logger.error(f"Error processing batch: {e}", exc_info=True)
        return jsonify({"success": False, "message": "Internal server error"}), 500


@events_bp.route("/stats", methods=["GET"])
def get_stats():
    """
    Get storage statistics

    Response:
    {
      "connected": true,
      "used_memory_human": "1.2M",
      "total_keys": 150
    }
    """
    try:
        stats = storage.get_stats()
        return jsonify(stats), 200
    except Exception as e:
        logger.error(f"Error getting stats: {e}", exc_info=True)
        return jsonify({"error": "Failed to get stats"}), 500
