"""
Time window utilities for bucketing events and queries
"""
from datetime import datetime, timedelta
from typing import List
from enum import Enum


class TimeWindow(str, Enum):
    """Time window types"""

    MINUTE = "1m"
    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"
    HOUR = "1h"
    DAY = "1d"
    WEEK = "1w"
    MONTH = "1M"


class TimeWindowBucketer:
    """
    Utility for bucketing timestamps into time windows
    Used for Redis key generation and time-based aggregations
    """

    @staticmethod
    def bucket_timestamp(timestamp: datetime, window: TimeWindow) -> str:
        """
        Convert timestamp to window bucket string

        Args:
            timestamp: Datetime to bucket
            window: Time window type

        Returns:
            Bucket string (e.g., "2025-10-16T10:00:00" for hourly)
        """
        if window == TimeWindow.MINUTE:
            return timestamp.strftime("%Y-%m-%dT%H:%M:00")
        elif window == TimeWindow.FIVE_MINUTES:
            minute = (timestamp.minute // 5) * 5
            return timestamp.strftime(f"%Y-%m-%dT%H:{minute:02d}:00")
        elif window == TimeWindow.FIFTEEN_MINUTES:
            minute = (timestamp.minute // 15) * 15
            return timestamp.strftime(f"%Y-%m-%dT%H:{minute:02d}:00")
        elif window == TimeWindow.HOUR:
            return timestamp.strftime("%Y-%m-%dT%H:00:00")
        elif window == TimeWindow.DAY:
            return timestamp.strftime("%Y-%m-%d")
        elif window == TimeWindow.WEEK:
            # ISO week format
            year, week, _ = timestamp.isocalendar()
            return f"{year}-W{week:02d}"
        elif window == TimeWindow.MONTH:
            return timestamp.strftime("%Y-%m")
        else:
            raise ValueError(f"Unknown window type: {window}")

    @staticmethod
    def parse_window_string(window_str: str) -> TimeWindow:
        """
        Parse window string to TimeWindow enum

        Args:
            window_str: String like "1h", "1d", "1w"

        Returns:
            TimeWindow enum
        """
        try:
            return TimeWindow(window_str)
        except ValueError:
            raise ValueError(
                f"Invalid window: {window_str}. "
                f"Valid options: {[w.value for w in TimeWindow]}"
            )

    @staticmethod
    def get_window_duration(window: TimeWindow) -> timedelta:
        """
        Get timedelta for a window type

        Args:
            window: TimeWindow enum

        Returns:
            timedelta representing window duration
        """
        durations = {
            TimeWindow.MINUTE: timedelta(minutes=1),
            TimeWindow.FIVE_MINUTES: timedelta(minutes=5),
            TimeWindow.FIFTEEN_MINUTES: timedelta(minutes=15),
            TimeWindow.HOUR: timedelta(hours=1),
            TimeWindow.DAY: timedelta(days=1),
            TimeWindow.WEEK: timedelta(weeks=1),
            TimeWindow.MONTH: timedelta(days=30),  # Approximate
        }
        return durations[window]

    @staticmethod
    def get_window_range(
        end_time: datetime, window: TimeWindow, count: int = 1
    ) -> List[str]:
        """
        Get list of window buckets going back in time

        Args:
            end_time: End timestamp
            window: Window type
            count: Number of windows to include

        Returns:
            List of bucket strings
        """
        buckets = []
        duration = TimeWindowBucketer.get_window_duration(window)

        for i in range(count):
            timestamp = end_time - (duration * i)
            bucket = TimeWindowBucketer.bucket_timestamp(timestamp, window)
            buckets.append(bucket)

        return buckets

    @staticmethod
    def get_retention_seconds(window: TimeWindow) -> int:
        """
        Get Redis TTL in seconds for a window type

        Args:
            window: Window type

        Returns:
            TTL in seconds
        """
        retention_multipliers = {
            TimeWindow.MINUTE: 60,  # Keep for 1 hour
            TimeWindow.FIVE_MINUTES: 144,  # Keep for 12 hours
            TimeWindow.FIFTEEN_MINUTES: 96,  # Keep for 1 day
            TimeWindow.HOUR: 168,  # Keep for 7 days
            TimeWindow.DAY: 90,  # Keep for 90 days
            TimeWindow.WEEK: 52,  # Keep for 52 weeks
            TimeWindow.MONTH: 24,  # Keep for 24 months
        }

        duration = TimeWindowBucketer.get_window_duration(window)
        multiplier = retention_multipliers[window]
        return int(duration.total_seconds() * multiplier)


class RedisKeyGenerator:
    """
    Generate consistent Redis keys for probabilistic data structures
    """

    @staticmethod
    def hll_key(metric: str, system: str, window: TimeWindow, timestamp: datetime) -> str:
        """
        Generate HyperLogLog key

        Args:
            metric: Metric name (e.g., "users", "ips")
            system: System name
            window: Time window
            timestamp: Event timestamp

        Returns:
            Redis key (e.g., "hll:users:prod:1h:2025-10-16T10:00:00")
        """
        bucket = TimeWindowBucketer.bucket_timestamp(timestamp, window)
        return f"hll:{metric}:{system}:{window.value}:{bucket}"

    @staticmethod
    def bloom_key(metric: str, system: str, window: TimeWindow, timestamp: datetime) -> str:
        """Generate Bloom filter key"""
        bucket = TimeWindowBucketer.bucket_timestamp(timestamp, window)
        return f"bloom:{metric}:{system}:{window.value}:{bucket}"

    @staticmethod
    def cms_key(metric: str, system: str, window: TimeWindow, timestamp: datetime) -> str:
        """Generate Count-Min Sketch key"""
        bucket = TimeWindowBucketer.bucket_timestamp(timestamp, window)
        return f"cms:{metric}:{system}:{window.value}:{bucket}"

    @staticmethod
    def topk_key(metric: str, system: str, window: TimeWindow, timestamp: datetime) -> str:
        """Generate TopK key"""
        bucket = TimeWindowBucketer.bucket_timestamp(timestamp, window)
        return f"topk:{metric}:{system}:{window.value}:{bucket}"

    @staticmethod
    def tdigest_key(metric: str, system: str, window: TimeWindow, timestamp: datetime) -> str:
        """
        Generate T-Digest key (NEW!)

        Args:
            metric: Metric name (e.g., "api_latency", "query_time")
            system: System name
            window: Time window
            timestamp: Event timestamp

        Returns:
            Redis key (e.g., "tdigest:api_latency:prod:1h:2025-10-16T10:00:00")
        """
        bucket = TimeWindowBucketer.bucket_timestamp(timestamp, window)
        return f"tdigest:{metric}:{system}:{window.value}:{bucket}"

    @staticmethod
    def event_stream_key() -> str:
        """Generate event stream pub/sub key"""
        return "events:stream"

    @staticmethod
    def compliance_snapshot_key(date: datetime) -> str:
        """Generate compliance snapshot key"""
        return f"compliance:snapshot:{date.strftime('%Y-%m-%d')}"
