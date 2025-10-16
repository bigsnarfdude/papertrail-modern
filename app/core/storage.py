"""
Redis storage layer for probabilistic data structures
Handles HyperLogLog, Bloom filters, Count-Min Sketch with time-windowing
"""
import json
import pickle
from datetime import datetime
from typing import Optional, List, Dict, Any
import redis
from redis import Redis

from app.config import settings
from app.core.sketches.hyperloglog import HyperLogLog
from app.core.sketches.bloom_filter import BloomFilter
from app.core.sketches.count_min import TopK, HeavyHittersDetector
from app.utils.time_windows import (
    TimeWindow,
    TimeWindowBucketer,
    RedisKeyGenerator,
)


class RedisStorage:
    """
    Redis storage abstraction for event processing
    Combines native Redis HLL with custom probabilistic structures
    """

    def __init__(self, redis_client: Optional[Redis] = None):
        """
        Initialize Redis storage

        Args:
            redis_client: Optional Redis client (creates new if None)
        """
        if redis_client:
            self.redis = redis_client
        else:
            self.redis = redis.from_url(
                settings.get_redis_url(),
                decode_responses=False,  # Handle bytes for serialization
            )

        self.key_gen = RedisKeyGenerator()
        self.bucketer = TimeWindowBucketer()

    def ping(self) -> bool:
        """Check Redis connection"""
        try:
            return self.redis.ping()
        except Exception:
            return False

    # =====================
    # HyperLogLog Operations (using Redis native HLL)
    # =====================

    def add_to_hll(
        self,
        metric: str,
        system: str,
        value: str,
        timestamp: Optional[datetime] = None,
        windows: Optional[List[TimeWindow]] = None,
    ) -> None:
        """
        Add value to HyperLogLog for distinct counting

        Args:
            metric: Metric name (e.g., "users", "ips")
            system: System name
            value: Value to add (will be hashed)
            timestamp: Event timestamp (default: now)
            windows: List of time windows to update (default: [1h, 1d])
        """
        timestamp = timestamp or datetime.utcnow()
        windows = windows or [TimeWindow.HOUR, TimeWindow.DAY]

        for window in windows:
            key = self.key_gen.hll_key(metric, system, window, timestamp)

            # Redis native PFADD for HyperLogLog
            self.redis.pfadd(key, value)

            # Set TTL
            ttl = self.bucketer.get_retention_seconds(window)
            self.redis.expire(key, ttl)

    def get_hll_cardinality(
        self, metric: str, system: str, window: TimeWindow, timestamp: Optional[datetime] = None
    ) -> int:
        """
        Get distinct count from HyperLogLog

        Args:
            metric: Metric name
            system: System name
            window: Time window
            timestamp: Query timestamp (default: now)

        Returns:
            Estimated distinct count
        """
        timestamp = timestamp or datetime.utcnow()
        key = self.key_gen.hll_key(metric, system, window, timestamp)

        # Redis native PFCOUNT
        return self.redis.pfcount(key)

    def merge_hll(
        self,
        metric: str,
        system: str,
        source_window: TimeWindow,
        dest_key: str,
        timestamps: List[datetime],
    ) -> int:
        """
        Merge multiple HyperLogLogs across time windows

        Args:
            metric: Metric name
            system: System name
            source_window: Source window type
            dest_key: Destination Redis key
            timestamps: List of timestamps to merge

        Returns:
            Merged cardinality estimate
        """
        source_keys = [
            self.key_gen.hll_key(metric, system, source_window, ts) for ts in timestamps
        ]

        # Redis native PFMERGE
        self.redis.pfmerge(dest_key, *source_keys)
        return self.redis.pfcount(dest_key)

    # =====================
    # Bloom Filter Operations
    # =====================

    def add_to_bloom(
        self,
        metric: str,
        system: str,
        value: str,
        timestamp: Optional[datetime] = None,
        window: TimeWindow = TimeWindow.DAY,
    ) -> None:
        """
        Add value to Bloom filter for membership testing

        Args:
            metric: Metric name
            system: System name
            value: Value to add
            timestamp: Event timestamp
            window: Time window
        """
        timestamp = timestamp or datetime.utcnow()
        key = self.key_gen.bloom_key(metric, system, window, timestamp)

        # Load existing Bloom filter or create new
        bloom = self._load_bloom(key)
        if bloom is None:
            bloom = BloomFilter(
                capacity=settings.BLOOM_CAPACITY, error_rate=settings.BLOOM_ERROR_RATE
            )

        bloom.add(value)

        # Save back to Redis
        self._save_bloom(key, bloom, window)

    def check_bloom(
        self,
        metric: str,
        system: str,
        value: str,
        timestamp: Optional[datetime] = None,
        window: TimeWindow = TimeWindow.DAY,
    ) -> bool:
        """
        Check if value exists in Bloom filter

        Args:
            metric: Metric name
            system: System name
            value: Value to check
            timestamp: Query timestamp
            window: Time window

        Returns:
            True if value might exist (or false positive)
            False if value definitely does NOT exist
        """
        timestamp = timestamp or datetime.utcnow()
        key = self.key_gen.bloom_key(metric, system, window, timestamp)

        bloom = self._load_bloom(key)
        if bloom is None:
            return False

        return bloom.contains(value)

    def _load_bloom(self, key: str) -> Optional[BloomFilter]:
        """Load Bloom filter from Redis"""
        data = self.redis.get(key)
        if data is None:
            return None
        return pickle.loads(data)

    def _save_bloom(self, key: str, bloom: BloomFilter, window: TimeWindow) -> None:
        """Save Bloom filter to Redis"""
        data = pickle.dumps(bloom)
        ttl = self.bucketer.get_retention_seconds(window)
        self.redis.setex(key, ttl, data)

    # =====================
    # TopK / Heavy Hitters Operations
    # =====================

    def add_to_topk(
        self,
        metric: str,
        system: str,
        value: str,
        count: int = 1,
        timestamp: Optional[datetime] = None,
        window: TimeWindow = TimeWindow.HOUR,
    ) -> None:
        """
        Add value to TopK tracker

        Args:
            metric: Metric name
            system: System name
            value: Value to track
            count: Increment amount
            timestamp: Event timestamp
            window: Time window
        """
        timestamp = timestamp or datetime.utcnow()
        key = self.key_gen.topk_key(metric, system, window, timestamp)

        # Load existing TopK or create new
        topk = self._load_topk(key)
        if topk is None:
            topk = TopK(k=100)

        topk.add(value, count)

        # Save back to Redis
        self._save_topk(key, topk, window)

    def get_topk(
        self,
        metric: str,
        system: str,
        k: int = 10,
        timestamp: Optional[datetime] = None,
        window: TimeWindow = TimeWindow.HOUR,
    ) -> List[Dict[str, Any]]:
        """
        Get top K items

        Args:
            metric: Metric name
            system: System name
            k: Number of items to return
            timestamp: Query timestamp
            window: Time window

        Returns:
            List of {"item": str, "count": int} dicts
        """
        timestamp = timestamp or datetime.utcnow()
        key = self.key_gen.topk_key(metric, system, window, timestamp)

        topk = self._load_topk(key)
        if topk is None:
            return []

        results = topk.top_k(k)
        return [{"item": item, "count": count} for item, count in results]

    def _load_topk(self, key: str) -> Optional[TopK]:
        """Load TopK from Redis"""
        data = self.redis.get(key)
        if data is None:
            return None
        return pickle.loads(data)

    def _save_topk(self, key: str, topk: TopK, window: TimeWindow) -> None:
        """Save TopK to Redis"""
        data = pickle.dumps(topk)
        ttl = self.bucketer.get_retention_seconds(window)
        self.redis.setex(key, ttl, data)

    # =====================
    # Event Stream (Pub/Sub)
    # =====================

    def publish_event(self, event: Dict[str, Any]) -> None:
        """
        Publish event to real-time stream

        Args:
            event: Event dictionary
        """
        channel = self.key_gen.event_stream_key()
        message = json.dumps(event, default=str)
        self.redis.publish(channel, message)

    def subscribe_to_events(self):
        """
        Subscribe to event stream

        Returns:
            Redis PubSub object
        """
        pubsub = self.redis.pubsub()
        channel = self.key_gen.event_stream_key()
        pubsub.subscribe(channel)
        return pubsub

    # =====================
    # Compliance Snapshots
    # =====================

    def save_compliance_snapshot(self, date: datetime, data: Dict[str, Any]) -> None:
        """
        Save daily compliance snapshot for auditing

        Args:
            date: Snapshot date
            data: Compliance data
        """
        key = self.key_gen.compliance_snapshot_key(date)
        self.redis.setex(key, 86400 * 90, json.dumps(data, default=str))  # 90 day retention

    def get_compliance_snapshot(self, date: datetime) -> Optional[Dict[str, Any]]:
        """
        Get compliance snapshot

        Args:
            date: Snapshot date

        Returns:
            Compliance data or None
        """
        key = self.key_gen.compliance_snapshot_key(date)
        data = self.redis.get(key)
        if data is None:
            return None
        return json.loads(data)

    # =====================
    # Utility Methods
    # =====================

    def get_all_keys(self, pattern: str = "*") -> List[str]:
        """
        Get all keys matching pattern

        Args:
            pattern: Redis key pattern

        Returns:
            List of keys
        """
        return [key.decode() if isinstance(key, bytes) else key for key in self.redis.keys(pattern)]

    def delete_keys(self, pattern: str) -> int:
        """
        Delete keys matching pattern

        Args:
            pattern: Redis key pattern

        Returns:
            Number of keys deleted
        """
        keys = self.redis.keys(pattern)
        if keys:
            return self.redis.delete(*keys)
        return 0

    def get_stats(self) -> Dict[str, Any]:
        """
        Get Redis storage statistics

        Returns:
            Stats dictionary
        """
        info = self.redis.info()
        return {
            "connected": True,
            "used_memory_human": info.get("used_memory_human"),
            "total_keys": info.get("db0", {}).get("keys", 0),
            "uptime_seconds": info.get("uptime_in_seconds"),
        }
