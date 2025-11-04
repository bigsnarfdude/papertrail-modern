"""
HyperLogLog Monoid implementation - Now powered by algesnake!

Enables composable cardinality estimation across:
- Time windows (merge hourly HLLs into daily)
- Systems (merge multiple system HLLs)
- Distributed workers (merge partial results)

MIGRATION NOTE: This now uses algesnake's optimized HyperLogLog implementation
with Pythonic operator overloading (+ operator for merging).
"""
from typing import List
from app.core.monoid import Monoid
from algesnake.approximate import HyperLogLog


class HLLMonoid(Monoid[HyperLogLog]):
    """
    Monoid for HyperLogLog sketches

    Example usage:
        # Create monoid
        monoid = HLLMonoid(precision=14)

        # Create individual HLLs for different hours
        hll_hour1 = monoid.zero()
        hll_hour1.add("user1")
        hll_hour1.add("user2")

        hll_hour2 = monoid.zero()
        hll_hour2.add("user2")  # duplicate
        hll_hour2.add("user3")

        # Merge to get daily total
        hll_day = monoid.plus(hll_hour1, hll_hour2)
        print(hll_day.cardinality())  # ~3 (deduplicates user2)
    """

    def __init__(self, precision: int = 14):
        """
        Initialize HLLMonoid

        Args:
            precision: HyperLogLog precision (4-16)
        """
        self.precision = precision

    def zero(self) -> HyperLogLog:
        """
        Identity element: empty HyperLogLog

        Returns:
            Empty HLL with specified precision
        """
        return HyperLogLog(precision=self.precision)

    def plus(self, a: HyperLogLog, b: HyperLogLog) -> HyperLogLog:
        """
        Combine two HyperLogLogs

        Args:
            a: First HLL
            b: Second HLL

        Returns:
            Merged HLL (union of both)

        Raises:
            ValueError: If HLLs have different precision

        Note: algesnake HyperLogLog supports the + operator natively!
        """
        if a.precision != b.precision:
            raise ValueError(
                f"Cannot merge HLLs with different precision: {a.precision} vs {b.precision}"
            )

        # Use algesnake's Pythonic + operator for merging
        return a + b

    def sum_time_windows(self, hlls: List[HyperLogLog]) -> HyperLogLog:
        """
        Merge multiple time windows into aggregate

        Args:
            hlls: List of HLLs from different time windows

        Returns:
            Combined HLL with deduplicated cardinality

        Example:
            # Merge 24 hourly HLLs into daily aggregate
            hourly_hlls = [hll_00, hll_01, ..., hll_23]
            daily_hll = monoid.sum_time_windows(hourly_hlls)
        """
        return self.sum(hlls)

    def sum_systems(self, hlls: List[HyperLogLog]) -> HyperLogLog:
        """
        Merge HLLs from multiple systems

        Args:
            hlls: List of HLLs from different systems

        Returns:
            Combined HLL with total unique users across systems

        Example:
            # Total unique users across all systems
            system_hlls = [hll_prod, hll_staging, hll_api]
            total_hll = monoid.sum_systems(system_hlls)
        """
        return self.sum(hlls)

    def merge_distributed(self, hlls: List[HyperLogLog]) -> HyperLogLog:
        """
        Merge HLLs from distributed workers

        Args:
            hlls: List of HLLs from different workers

        Returns:
            Combined HLL

        Example:
            # Merge results from parallel processing
            worker_hlls = [worker1_hll, worker2_hll, worker3_hll]
            final_hll = monoid.merge_distributed(worker_hlls)
        """
        return self.sum(hlls)


class HLLMonoidWithTimestamp(Monoid[tuple]):
    """
    HLL Monoid that tracks most recent timestamp

    Useful for knowing when data was last updated
    """

    def __init__(self, precision: int = 14):
        self.hll_monoid = HLLMonoid(precision)

    def zero(self) -> tuple:
        """Returns (empty HLL, timestamp=0)"""
        return (self.hll_monoid.zero(), 0)

    def plus(self, a: tuple, b: tuple) -> tuple:
        """
        Merge HLLs and take max timestamp

        Args:
            a: (HLL, timestamp)
            b: (HLL, timestamp)

        Returns:
            (merged HLL, max timestamp)
        """
        hll_a, ts_a = a
        hll_b, ts_b = b

        merged_hll = self.hll_monoid.plus(hll_a, hll_b)
        max_ts = max(ts_a, ts_b)

        return (merged_hll, max_ts)
