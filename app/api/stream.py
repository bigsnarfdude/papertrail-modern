"""
Server-Sent Events (SSE) streaming API
Real-time event updates for dashboard
"""
from flask import Blueprint, Response
import json
import time
import logging

from app.core.storage import RedisStorage
from app.config import settings

logger = logging.getLogger(__name__)

stream_bp = Blueprint("stream", __name__, url_prefix="/api/v1")

storage = RedisStorage()


def event_stream():
    """
    Generator function for SSE events
    Subscribes to Redis pub/sub and yields events
    """
    pubsub = storage.subscribe_to_events()

    try:
        # Send initial connection message
        yield f"data: {json.dumps({'type': 'connected', 'message': 'Stream connected'})}\n\n"

        last_heartbeat = time.time()

        for message in pubsub.listen():
            # Handle Redis pub/sub messages
            if message["type"] == "message":
                # Parse and forward event
                try:
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")

                    yield f"data: {data}\n\n"

                except Exception as e:
                    logger.error(f"Error processing message: {e}")

            # Send periodic heartbeat to keep connection alive
            current_time = time.time()
            if current_time - last_heartbeat > settings.SSE_HEARTBEAT_INTERVAL:
                yield f": heartbeat\n\n"
                last_heartbeat = current_time

    except GeneratorExit:
        logger.info("Client disconnected from event stream")
        pubsub.close()
    except Exception as e:
        logger.error(f"Error in event stream: {e}", exc_info=True)
        pubsub.close()
        raise


@stream_bp.route("/stream", methods=["GET"])
def stream_events():
    """
    SSE endpoint for real-time event streaming

    Usage (JavaScript):
    ```javascript
    const eventSource = new EventSource('/api/v1/stream');

    eventSource.onmessage = function(event) {
      const data = JSON.parse(event.data);
      console.log('Received event:', data);
    };

    eventSource.onerror = function(error) {
      console.error('SSE error:', error);
    };
    ```

    Response: text/event-stream
    """
    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
            "Connection": "keep-alive",
        },
    )


@stream_bp.route("/stream/test", methods=["POST"])
def test_stream():
    """
    Test endpoint to publish test event to stream

    Request Body:
    {
      "message": "Test event"
    }

    Response:
    {
      "success": true,
      "message": "Event published"
    }
    """
    try:
        from flask import request

        data = request.get_json() or {}
        test_event = {
            "type": "test",
            "message": data.get("message", "Test event"),
            "timestamp": time.time(),
        }

        storage.publish_event(test_event)

        return json.dumps({"success": True, "message": "Event published"}), 200

    except Exception as e:
        logger.error(f"Error publishing test event: {e}", exc_info=True)
        return json.dumps({"success": False, "error": str(e)}), 500
