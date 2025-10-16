"""
Examples of Monoid-based aggregations

Demonstrates Algebird-style composable event processing
"""
from datetime import datetime, timedelta
from app.core.monoids.hll_monoid import HLLMonoid
from app.core.monoids.bloom_monoid import BloomFilterUnionMonoid
from app.core.monoids.topk_monoid import TopKMonoid
from app.core.monoids.moments_monoid import MomentsMonoid, RunningStatistics
from app.core.aggregations import (
    HLLTimeWindowAggregator,
    MultiSystemAggregator,
    CompositeAggregator,
)


def example_1_merge_hourly_to_daily():
    """
    Example 1: Merge 24 hourly HLLs into daily aggregate

    Use case: Get total unique users for the day from hourly data
    """
    print("=" * 60)
    print("Example 1: Hourly -> Daily Aggregation (HyperLogLog)")
    print("=" * 60)

    monoid = HLLMonoid(precision=14)

    # Simulate 24 hours of user activity
    hourly_hlls = {}
    for hour in range(24):
        hll = monoid.zero()

        # Each hour has different users (with some overlap)
        for user_id in range(hour * 40, hour * 40 + 100):
            hll.add(f"user_{user_id % 500}")  # Modulo creates natural overlap

        timestamp = f"2025-10-16T{hour:02d}:00:00"
        hourly_hlls[timestamp] = hll
        print(f"  Hour {hour:02d}: {hll.cardinality()} unique users")

    # Merge all hourly HLLs into daily total
    daily_hll = monoid.sum(list(hourly_hlls.values()))

    print(f"\n  Daily Total: {daily_hll.cardinality()} unique users (deduplicated)")
    print(f"  Memory: ~12 KB per HLL (vs {daily_hll.cardinality() * 36} bytes raw)")
    print()


def example_2_merge_across_systems():
    """
    Example 2: Merge HLLs from multiple systems

    Use case: Total unique users across production + staging + API gateway
    """
    print("=" * 60)
    print("Example 2: Multi-System Aggregation (HyperLogLog)")
    print("=" * 60)

    monoid = HLLMonoid(precision=14)

    # Create HLLs for different systems
    systems = {}

    # Production DB: 1000 users
    systems["production_db"] = monoid.zero()
    for i in range(1000):
        systems["production_db"].add(f"user_{i}")

    # Staging DB: 500 users (some overlap with prod)
    systems["staging_db"] = monoid.zero()
    for i in range(400, 900):  # 400-899
        systems["staging_db"].add(f"user_{i}")

    # API Gateway: 800 users (some overlap)
    systems["api_gateway"] = monoid.zero()
    for i in range(200, 1000):  # 200-999
        systems["api_gateway"].add(f"user_{i}")

    # Print per-system counts
    for system_name, hll in systems.items():
        print(f"  {system_name}: {hll.cardinality()} unique users")

    # Merge across all systems
    aggregator = MultiSystemAggregator(monoid)
    total_hll = aggregator.aggregate_systems(systems)

    print(f"\n  Total Unique Users: {total_hll.cardinality()} (across all systems)")
    print()


def example_3_bloom_filter_union():
    """
    Example 3: Union of Bloom filters across time windows

    Use case: Check if user was active ANY time during the day
    """
    print("=" * 60)
    print("Example 3: Bloom Filter Time Window Union")
    print("=" * 60)

    monoid = BloomFilterUnionMonoid(capacity=10000, error_rate=0.001)

    # Simulate hourly activity
    hourly_filters = []
    for hour in range(24):
        bf = monoid.zero()

        # Each hour has different active users
        for user_id in range(hour * 20, hour * 20 + 50):
            bf.add(f"user_{user_id}")

        hourly_filters.append(bf)
        print(f"  Hour {hour:02d}: {bf.estimated_count()} active users")

    # Union all hourly filters
    daily_filter = monoid.sum(hourly_filters)

    print(f"\n  Daily Activity Filter created")

    # Check specific users
    test_users = ["user_50", "user_500", "user_1000"]
    for user in test_users:
        active = user in daily_filter
        print(f"  {user}: {'ACTIVE' if active else 'INACTIVE'} today")

    print()


def example_4_topk_merge():
    """
    Example 4: Merge TopK heavy hitters

    Use case: Top 10 most active users for the day from hourly data
    """
    print("=" * 60)
    print("Example 4: TopK Heavy Hitters Merge")
    print("=" * 60)

    monoid = TopKMonoid(k=10)

    # Simulate hourly top users
    hourly_topk = []
    for hour in range(24):
        topk = monoid.zero()

        # Simulate user activity (some users more active)
        for user_id in range(hour * 5, hour * 5 + 20):
            count = user_id % 50  # Creates varying activity levels
            topk.add(f"user_{user_id % 100}", count)

        hourly_topk.append(topk)

    # Merge all hourly TopK
    daily_topk = monoid.sum(hourly_topk)

    print("  Top 10 Most Active Users Today:")
    for rank, (user, count) in enumerate(daily_topk.top_k(10), 1):
        print(f"    {rank}. {user}: {count} actions")

    print()


def example_5_running_statistics():
    """
    Example 5: Running statistics with Moments Monoid

    Use case: Track mean/variance/stddev of response times
    """
    print("=" * 60)
    print("Example 5: Running Statistics (Moments)")
    print("=" * 60)

    monoid = MomentsMonoid()

    # Simulate hourly response time statistics
    hourly_moments = []
    for hour in range(24):
        # Response times for this hour (in milliseconds)
        response_times = [100 + hour * 5 + i for i in range(100)]

        moments = monoid.from_values(response_times)
        hourly_moments.append(moments)

        print(f"  Hour {hour:02d}: mean={moments.mean:.1f}ms, stddev={moments.stddev:.1f}ms")

    # Merge into daily statistics
    daily_moments = monoid.sum(hourly_moments)

    print(f"\n  Daily Statistics:")
    print(f"    Count: {daily_moments.count}")
    print(f"    Mean: {daily_moments.mean:.2f}ms")
    print(f"    StdDev: {daily_moments.stddev:.2f}ms")
    print(f"    Min: ~{daily_moments.mean - 2*daily_moments.stddev:.2f}ms")
    print(f"    Max: ~{daily_moments.mean + 2*daily_moments.stddev:.2f}ms")
    print()


def example_6_composite_aggregation():
    """
    Example 6: Aggregate across BOTH time and systems

    Use case: Total unique users across all systems and all time periods
    """
    print("=" * 60)
    print("Example 6: Composite Time + System Aggregation")
    print("=" * 60)

    monoid = HLLMonoid(precision=14)
    aggregator = CompositeAggregator(monoid)

    # Data structure: {system_name: {time_window: HLL}}
    data = {}

    systems = ["prod", "staging", "api"]
    for system in systems:
        data[system] = {}
        for hour in range(24):
            hll = monoid.zero()

            # Each system has different user base
            base = {"prod": 0, "staging": 500, "api": 800}[system]
            for i in range(base, base + 200):
                hll.add(f"user_{i % 1000}")

            timestamp = f"2025-10-16T{hour:02d}:00:00"
            data[system][timestamp] = hll

    # Aggregate by system (across all time)
    by_system = aggregator.aggregate_by_system(data)
    print("  Unique Users by System (daily):")
    for system, hll in by_system.items():
        print(f"    {system}: {hll.cardinality()}")

    # Aggregate by time (across all systems)
    by_time = aggregator.aggregate_by_time(data)
    print(f"\n  Hourly Unique Users (across all systems):")
    for hour in range(0, 24, 6):  # Show every 6 hours
        timestamp = f"2025-10-16T{hour:02d}:00:00"
        if timestamp in by_time:
            print(f"    Hour {hour:02d}: {by_time[timestamp].cardinality()}")

    # Total across everything
    total = aggregator.aggregate_time_and_systems(data)
    print(f"\n  Total Unique Users (all systems, all day): {total.cardinality()}")
    print()


if __name__ == "__main__":
    example_1_merge_hourly_to_daily()
    example_2_merge_across_systems()
    example_3_bloom_filter_union()
    example_4_topk_merge()
    example_5_running_statistics()
    example_6_composite_aggregation()

    print("=" * 60)
    print("All examples completed!")
    print("=" * 60)
