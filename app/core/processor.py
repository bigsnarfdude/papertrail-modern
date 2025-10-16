"""
Event processing engine
Handles incoming events and updates probabilistic data structures
"""
from datetime import datetime
from typing import List
import logging

from app.models.events import Event
from app.core.storage import RedisStorage
from app.utils.time_windows import TimeWindow

logger = logging.getLogger(__name__)


class EventProcessor:
    """
    Process events and update probabilistic data structures
    """

    def __init__(self, storage: RedisStorage):
        """
        Initialize event processor

        Args:
            storage: Redis storage instance
        """
        self.storage = storage

    def process_event(self, event: Event) -> None:
        """
        Process a single event

        Args:
            event: Event to process
        """
        try:
            # Update HyperLogLog for distinct counts
            self._update_hll(event)

            # Update Bloom filter for activity tracking
            self._update_bloom(event)

            # Update TopK for heavy hitters
            self._update_topk(event)

            # Publish to real-time stream
            self._publish_event(event)

            logger.debug(f"Processed event: {event.event_type} for system {event.system}")

        except Exception as e:
            logger.error(f"Error processing event: {e}", exc_info=True)
            raise

    def process_batch(self, events: List[Event]) -> int:
        """
        Process multiple events

        Args:
            events: List of events

        Returns:
            Number of successfully processed events
        """
        success_count = 0
        for event in events:
            try:
                self.process_event(event)
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to process event: {e}")

        return success_count

    def _update_hll(self, event: Event) -> None:
        """
        Update HyperLogLog sketches for distinct counting

        Tracks:
        - Unique users per system
        - Unique sessions per system
        - Unique IPs per event type
        """
        # Track unique users
        if event.user_id:
            self.storage.add_to_hll(
                metric="users",
                system=event.system,
                value=event.user_id,
                timestamp=event.timestamp,
                windows=[TimeWindow.HOUR, TimeWindow.DAY, TimeWindow.WEEK],
            )

        # Track unique sessions
        if event.session_id:
            self.storage.add_to_hll(
                metric="sessions",
                system=event.system,
                value=event.session_id,
                timestamp=event.timestamp,
                windows=[TimeWindow.HOUR, TimeWindow.DAY],
            )

        # Track unique IPs
        if "ip" in event.metadata:
            self.storage.add_to_hll(
                metric="ips",
                system=event.system,
                value=event.metadata["ip"],
                timestamp=event.timestamp,
                windows=[TimeWindow.HOUR, TimeWindow.DAY],
            )

    def _update_bloom(self, event: Event) -> None:
        """
        Update Bloom filters for activity tracking

        Tracks:
        - User activity per system (for "did user X access system Y?" queries)
        - IP activity per system
        """
        # Track user activity
        if event.user_id:
            self.storage.add_to_bloom(
                metric="user_activity",
                system=event.system,
                value=f"{event.user_id}:{event.system}",
                timestamp=event.timestamp,
                window=TimeWindow.DAY,
            )

            # Also track weekly for longer-term queries
            self.storage.add_to_bloom(
                metric="user_activity",
                system=event.system,
                value=f"{event.user_id}:{event.system}",
                timestamp=event.timestamp,
                window=TimeWindow.WEEK,
            )

        # Track IP activity for security monitoring
        if "ip" in event.metadata:
            self.storage.add_to_bloom(
                metric="ip_activity",
                system=event.system,
                value=event.metadata["ip"],
                timestamp=event.timestamp,
                window=TimeWindow.DAY,
            )

    def _update_topk(self, event: Event) -> None:
        """
        Update TopK for heavy hitters

        Tracks:
        - Most active users
        - Most active IPs
        - Most common event types
        - Most accessed endpoints (if in metadata)
        """
        # Track most active users
        if event.user_id:
            self.storage.add_to_topk(
                metric="active_users",
                system=event.system,
                value=event.user_id,
                timestamp=event.timestamp,
                window=TimeWindow.HOUR,
            )

        # Track most active IPs
        if "ip" in event.metadata:
            self.storage.add_to_topk(
                metric="active_ips",
                system=event.system,
                value=event.metadata["ip"],
                timestamp=event.timestamp,
                window=TimeWindow.HOUR,
            )

        # Track event types
        self.storage.add_to_topk(
            metric="event_types",
            system=event.system,
            value=event.event_type,
            timestamp=event.timestamp,
            window=TimeWindow.HOUR,
        )

        # Track endpoints if available
        if "endpoint" in event.metadata:
            self.storage.add_to_topk(
                metric="endpoints",
                system=event.system,
                value=event.metadata["endpoint"],
                timestamp=event.timestamp,
                window=TimeWindow.HOUR,
            )

        # Track error codes for security events
        if event.event_type == "security_event" and "status_code" in event.metadata:
            self.storage.add_to_topk(
                metric="failed_logins",
                system=event.system,
                value=event.metadata.get("ip", "unknown"),
                timestamp=event.timestamp,
                window=TimeWindow.HOUR,
            )

    def _publish_event(self, event: Event) -> None:
        """
        Publish event to real-time stream for SSE

        Args:
            event: Event to publish
        """
        event_dict = {
            "event_type": event.event_type,
            "system": event.system,
            "user_id": event.user_id,
            "timestamp": event.timestamp.isoformat(),
            "metadata": event.metadata,
        }
        self.storage.publish_event(event_dict)

    def get_metrics_summary(self, system: str, timestamp: Optional[datetime] = None) -> dict:
        """
        Get summary of metrics for a system

        Args:
            system: System name
            timestamp: Query timestamp (default: now)

        Returns:
            Dictionary of metrics
        """
        timestamp = timestamp or datetime.utcnow()

        return {
            "system": system,
            "timestamp": timestamp.isoformat(),
            "hourly": {
                "unique_users": self.storage.get_hll_cardinality(
                    "users", system, TimeWindow.HOUR, timestamp
                ),
                "unique_sessions": self.storage.get_hll_cardinality(
                    "sessions", system, TimeWindow.HOUR, timestamp
                ),
                "unique_ips": self.storage.get_hll_cardinality(
                    "ips", system, TimeWindow.HOUR, timestamp
                ),
                "top_users": self.storage.get_topk(
                    "active_users", system, k=10, timestamp=timestamp, window=TimeWindow.HOUR
                ),
                "top_ips": self.storage.get_topk(
                    "active_ips", system, k=10, timestamp=timestamp, window=TimeWindow.HOUR
                ),
            },
            "daily": {
                "unique_users": self.storage.get_hll_cardinality(
                    "users", system, TimeWindow.DAY, timestamp
                ),
                "unique_sessions": self.storage.get_hll_cardinality(
                    "sessions", system, TimeWindow.DAY, timestamp
                ),
                "unique_ips": self.storage.get_hll_cardinality(
                    "ips", system, TimeWindow.DAY, timestamp
                ),
            },
        }
