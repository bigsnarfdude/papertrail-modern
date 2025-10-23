"""
Aggregation utilities using Monoids

High-level operations for:
- Time window merging
- Multi-system aggregation
- Distributed processing
"""
from datetime import datetime, timedelta
from typing import List, Dict, Optional, TypeVar, Generic
import logging

from app.core.monoid import Monoid
from app.core.monoids.hll_monoid import HLLMonoid
from app.core.monoids.bloom_monoid import BloomFilterUnionMonoid
from app.core.monoids.topk_monoid import TopKMonoid
from app.core.monoids.moments_monoid import MomentsMonoid
from app.utils.time_windows import TimeWindow, TimeWindowBucketer
# Use algesnake implementations
from algesnake.approximate import HyperLogLog, BloomFilter, TopK
from app.core.monoids.moments_monoid import Moments

logger = logging.getLogger(__name__)

T = TypeVar('T')


class TimeWindowAggregator(Generic[T]):
    """
    Generic time window aggregator using monoids

    Merges data structures across time windows using monoid operations
    """

    def __init__(self, monoid: Monoid[T]):
        """
        Initialize aggregator

        Args:
            monoid: Monoid instance for the data type
        """
        self.monoid = monoid

    def aggregate_windows(
        self,
        windows: Dict[str, T],
        window_keys: Optional[List[str]] = None
    ) -> T:
        """
        Aggregate data from multiple time windows

        Args:
            windows: Dict mapping window bucket string to data structure
            window_keys: Optional list of specific keys to aggregate (all if None)

        Returns:
            Aggregated result

        Example:
            # Merge hourly HLLs into daily
            aggregator = TimeWindowAggregator(HLLMonoid(precision=14))
            hourly_hlls = {
                "2025-10-16T00:00:00": hll_00,
                "2025-10-16T01:00:00": hll_01,
                # ...
            }
            daily_hll = aggregator.aggregate_windows(hourly_hlls)
        """
        if window_keys:
            items = [windows[key] for key in window_keys if key in windows]
        else:
            items = list(windows.values())

        return self.monoid.sum(items)

    def aggregate_last_n_windows(
        self,
        windows: Dict[str, T],
        n: int,
        sorted_keys: Optional[List[str]] = None
    ) -> T:
        """
        Aggregate last N time windows

        Args:
            windows: Dict mapping window bucket to data structure
            n: Number of recent windows to include
            sorted_keys: Optional pre-sorted list of window keys (most recent first)

        Returns:
            Aggregated result

        Example:
            # Last 24 hours from hourly data
            aggregator = TimeWindowAggregator(HLLMonoid())
            daily = aggregator.aggregate_last_n_windows(hourly_hlls, n=24)
        """
        if sorted_keys is None:
            sorted_keys = sorted(windows.keys(), reverse=True)

        recent_keys = sorted_keys[:n]
        return self.aggregate_windows(windows, recent_keys)


class HLLTimeWindowAggregator:
    """
    Specialized aggregator for HyperLogLog time windows

    Provides convenient methods for common HLL aggregation patterns
    """

    def __init__(self, precision: int = 14):
        self.monoid = HLLMonoid(precision=precision)
        self.aggregator = TimeWindowAggregator(self.monoid)

    def hourly_to_daily(self, hourly_hlls: Dict[str, HyperLogLog]) -> HyperLogLog:
        """
        Merge 24 hourly HLLs into daily aggregate

        Args:
            hourly_hlls: Dict of hourly HLLs keyed by timestamp

        Returns:
            Daily HLL with deduplicated cardinality

        Note: With algesnake, this is now a simple sum()!
        """
        # Use algesnake's native sum() - much simpler!
        return sum(hourly_hlls.values())

    def daily_to_weekly(self, daily_hlls: Dict[str, HyperLogLog]) -> HyperLogLog:
        """
        Merge 7 daily HLLs into weekly aggregate

        Args:
            daily_hlls: Dict of daily HLLs keyed by date

        Returns:
            Weekly HLL

        Note: With algesnake, this is now a simple sum()!
        """
        # Use algesnake's native sum() - much simpler!
        return sum(daily_hlls.values())

    def rolling_window(
        self,
        hourly_hlls: Dict[str, HyperLogLog],
        hours: int = 24
    ) -> HyperLogLog:
        """
        Create rolling window aggregate (e.g., last 24 hours)

        Args:
            hourly_hlls: Dict of hourly HLLs
            hours: Number of hours to include

        Returns:
            HLL for rolling window
        """
        return self.aggregator.aggregate_last_n_windows(hourly_hlls, n=hours)


class MultiSystemAggregator(Generic[T]):
    """
    Aggregate data across multiple systems using monoids
    """

    def __init__(self, monoid: Monoid[T]):
        self.monoid = monoid

    def aggregate_systems(self, systems: Dict[str, T]) -> T:
        """
        Aggregate data across all systems

        Args:
            systems: Dict mapping system name to data structure

        Returns:
            Combined result across all systems

        Example:
            # Total unique users across all systems
            aggregator = MultiSystemAggregator(HLLMonoid())
            system_hlls = {
                "production_db": hll_prod,
                "staging_db": hll_staging,
                "api_gateway": hll_api
            }
            total = aggregator.aggregate_systems(system_hlls)
        """
        return self.monoid.sum(list(systems.values()))

    def aggregate_subset(self, systems: Dict[str, T], system_names: List[str]) -> T:
        """
        Aggregate data from specific systems

        Args:
            systems: Dict of all systems
            system_names: List of system names to include

        Returns:
            Aggregated result for specified systems
        """
        items = [systems[name] for name in system_names if name in systems]
        return self.monoid.sum(items)


class DistributedAggregator(Generic[T]):
    """
    Aggregate results from distributed workers using monoids

    Useful for parallel/distributed event processing
    """

    def __init__(self, monoid: Monoid[T]):
        self.monoid = monoid

    def aggregate_workers(self, worker_results: List[T]) -> T:
        """
        Merge results from multiple workers

        Args:
            worker_results: List of results from different workers

        Returns:
            Combined result

        Example:
            # Merge HLLs from parallel workers
            aggregator = DistributedAggregator(HLLMonoid())
            worker_hlls = [worker1_hll, worker2_hll, worker3_hll]
            final = aggregator.aggregate_workers(worker_hlls)
        """
        return self.monoid.sum(worker_results)

    def aggregate_with_metadata(
        self,
        worker_results: Dict[str, T]
    ) -> tuple:
        """
        Aggregate with worker metadata

        Args:
            worker_results: Dict mapping worker_id to result

        Returns:
            (combined_result, worker_count, worker_ids)
        """
        results = list(worker_results.values())
        combined = self.monoid.sum(results)
        return (combined, len(results), list(worker_results.keys()))


class CompositeAggregator:
    """
    Aggregate across both time windows AND systems

    Combines time-based and system-based aggregation
    """

    def __init__(self, monoid: Monoid[T]):
        self.monoid = monoid
        self.time_agg = TimeWindowAggregator(monoid)
        self.system_agg = MultiSystemAggregator(monoid)

    def aggregate_time_and_systems(
        self,
        data: Dict[str, Dict[str, T]]
    ) -> T:
        """
        Aggregate across both dimensions

        Args:
            data: Nested dict: {system_name: {time_window: data_structure}}

        Returns:
            Total aggregate across all systems and time windows

        Example:
            # Total unique users across all systems and all time
            aggregator = CompositeAggregator(HLLMonoid())
            data = {
                "prod": {
                    "2025-10-16T00:00:00": hll_prod_00,
                    "2025-10-16T01:00:00": hll_prod_01,
                },
                "staging": {
                    "2025-10-16T00:00:00": hll_staging_00,
                    "2025-10-16T01:00:00": hll_staging_01,
                }
            }
            total = aggregator.aggregate_time_and_systems(data)
        """
        all_items = []
        for system_data in data.values():
            all_items.extend(system_data.values())

        return self.monoid.sum(all_items)

    def aggregate_by_system(
        self,
        data: Dict[str, Dict[str, T]]
    ) -> Dict[str, T]:
        """
        Aggregate time windows per system

        Args:
            data: Nested dict: {system_name: {time_window: data_structure}}

        Returns:
            Dict mapping system_name to time-aggregated result

        Example:
            # Unique users per system (across all time)
            result = aggregator.aggregate_by_system(data)
            # {"prod": HLL(...), "staging": HLL(...)}
        """
        result = {}
        for system_name, time_windows in data.items():
            result[system_name] = self.time_agg.aggregate_windows(time_windows)
        return result

    def aggregate_by_time(
        self,
        data: Dict[str, Dict[str, T]]
    ) -> Dict[str, T]:
        """
        Aggregate systems per time window

        Args:
            data: Nested dict: {system_name: {time_window: data_structure}}

        Returns:
            Dict mapping time_window to system-aggregated result

        Example:
            # Unique users per hour (across all systems)
            result = aggregator.aggregate_by_time(data)
            # {"2025-10-16T00:00:00": HLL(...), ...}
        """
        # Invert the nesting: time_window -> {system: data}
        time_to_systems = {}
        for system_name, time_windows in data.items():
            for time_window, data_structure in time_windows.items():
                if time_window not in time_to_systems:
                    time_to_systems[time_window] = {}
                time_to_systems[time_window][system_name] = data_structure

        # Aggregate per time window
        result = {}
        for time_window, system_data in time_to_systems.items():
            result[time_window] = self.system_agg.aggregate_systems(system_data)

        return result


# ============================================================
# Convenience functions for common patterns
# ============================================================

def merge_hourly_to_daily_hll(hourly_hlls: List[HyperLogLog]) -> HyperLogLog:
    """
    Convenience: Merge hourly HLLs into daily

    Args:
        hourly_hlls: List of 24 hourly HLLs

    Returns:
        Daily HLL

    Note: With algesnake, this is now a simple sum()!
    """
    if not hourly_hlls:
        return HyperLogLog()

    # Use algesnake's native sum() - much simpler!
    return sum(hourly_hlls)


def merge_systems_hll(system_hlls: Dict[str, HyperLogLog]) -> HyperLogLog:
    """
    Convenience: Merge HLLs from multiple systems

    Args:
        system_hlls: Dict mapping system name to HLL

    Returns:
        Combined HLL

    Note: With algesnake, this is now a simple sum()!
    """
    if not system_hlls:
        return HyperLogLog()

    # Use algesnake's native sum() - much simpler!
    return sum(system_hlls.values())


def merge_topk_windows(topk_list: List[TopK]) -> TopK:
    """
    Convenience: Merge TopK from multiple windows

    Args:
        topk_list: List of TopK trackers

    Returns:
        Merged TopK

    Note: With algesnake, this is now a simple sum()!
    """
    if not topk_list:
        return TopK()

    # Use algesnake's native sum() - much simpler!
    return sum(topk_list)
