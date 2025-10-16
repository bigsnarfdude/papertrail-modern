# Monoids: Algebird-Style Composable Aggregations

## Overview

This system implements **Monoid abstractions** inspired by [Twitter Algebird](https://github.com/twitter/algebird), enabling composable, distributed, and incremental event processing with probabilistic data structures.

## What is a Monoid?

A **Monoid** is an algebraic structure with two key properties:

1. **Identity Element (`zero`)**: An element that, when combined with any other element, leaves it unchanged
2. **Associative Operation (`plus`)**: A combining operation where order of grouping doesn't matter

### Monoid Laws

```python
# Identity
plus(zero, x) == x
plus(x, zero) == x

# Associativity
plus(plus(a, b), c) == plus(a, plus(b, c))
```

### Why Monoids Matter for Event Processing

1. **Composability**: Results can be combined without recomputation
2. **Distributed Processing**: Merge results from multiple workers/servers
3. **Time Window Merging**: Combine hourly → daily → weekly aggregates
4. **Incremental Updates**: Add new data without recalculating everything

## Architecture

```
Event Stream
     ↓
Probabilistic Data Structures
     ↓
Monoid Operations
     ↓
Time Window / System / Distributed Aggregation
```

## Implemented Monoids

### 1. HyperLogLog Monoid

**Purpose**: Composable distinct counting

**Use Case**: "How many unique users visited today across all systems?"

```python
from app.core.monoids.hll_monoid import HLLMonoid

monoid = HLLMonoid(precision=14)

# Create HLLs for different systems
hll_prod = monoid.zero()
hll_prod.add("user1")
hll_prod.add("user2")

hll_staging = monoid.zero()
hll_staging.add("user2")  # duplicate
hll_staging.add("user3")

# Merge (automatically deduplicates)
hll_total = monoid.plus(hll_prod, hll_staging)
print(hll_total.cardinality())  # ~3 unique users
```

**Operations**:
- `zero()` - Empty HLL
- `plus(a, b)` - Merge two HLLs
- `sum(list)` - Merge multiple HLLs
- `sum_time_windows(list)` - Merge hourly → daily
- `sum_systems(list)` - Merge across systems

**Memory**: ~12 KB per HLL, regardless of cardinality

### 2. Bloom Filter Monoid

**Purpose**: Composable membership testing

**Use Case**: "Was user X active in ANY system today?"

```python
from app.core.monoids.bloom_monoid import BloomFilterUnionMonoid

monoid = BloomFilterUnionMonoid(capacity=1_000_000, error_rate=0.001)

# Create filters for different time windows
bf_morning = monoid.zero()
bf_morning.add("user1")

bf_afternoon = monoid.zero()
bf_afternoon.add("user2")

# Union (OR operation)
bf_day = monoid.plus(bf_morning, bf_afternoon)
print("user1" in bf_day)  # True
```

**Operations**:
- `zero()` - Empty Bloom filter
- `plus(a, b)` - Union of filters
- `sum(list)` - Union of multiple filters

**Memory**: ~1.2 MB for 1M items with 0.1% error rate

### 3. TopK Monoid

**Purpose**: Composable heavy hitter tracking

**Use Case**: "Who are the top 10 most active users today?"

```python
from app.core.monoids.topk_monoid import TopKMonoid

monoid = TopKMonoid(k=10)

# Track activity in different time windows
topk_morning = monoid.zero()
topk_morning.add("user1", 100)  # 100 actions
topk_morning.add("user2", 50)

topk_afternoon = monoid.zero()
topk_afternoon.add("user1", 75)  # same user, more actions
topk_afternoon.add("user3", 60)

# Merge (counts add up)
topk_day = monoid.plus(topk_morning, topk_afternoon)
print(topk_day.top_k(3))
# [("user1", 175), ("user3", 60), ("user2", 50)]
```

**Operations**:
- `zero()` - Empty TopK tracker
- `plus(a, b)` - Merge TopK (adds counts)
- `sum_time_windows(list)` - Merge hourly → daily tops

**Memory**: O(k) space (typically ~12 KB for k=100)

### 4. Moments Monoid

**Purpose**: Composable statistical aggregation

**Use Case**: "What's the mean/variance of response times today?"

```python
from app.core.monoids.moments_monoid import MomentsMonoid

monoid = MomentsMonoid()

# Statistics from morning traffic
m1 = monoid.from_values([100, 110, 120, 130, 140])  # response times in ms

# Statistics from afternoon traffic
m2 = monoid.from_values([105, 115, 125, 135, 145])

# Merge statistics (numerically stable)
m_day = monoid.plus(m1, m2)

print(f"Count: {m_day.count}")
print(f"Mean: {m_day.mean:.2f}ms")
print(f"StdDev: {m_day.stddev:.2f}ms")
print(f"Variance: {m_day.variance:.2f}")
```

**Operations**:
- `zero()` - No observations
- `plus(a, b)` - Merge statistics (Welford's algorithm)
- `from_values(list)` - Create from raw data
- Properties: `mean`, `variance`, `stddev`, `skewness`, `kurtosis`

**Memory**: O(1) - fixed 5 floating point values

## Aggregation Patterns

### Pattern 1: Time Window Aggregation

Merge smaller time windows into larger ones:

```python
from app.core.aggregations import HLLTimeWindowAggregator

aggregator = HLLTimeWindowAggregator(precision=14)

# Hourly data
hourly_hlls = {
    "2025-10-16T00:00:00": hll_00,
    "2025-10-16T01:00:00": hll_01,
    # ... 24 hours
}

# Merge into daily
daily_hll = aggregator.hourly_to_daily(hourly_hlls)
print(daily_hll.cardinality())  # Total unique users for day
```

### Pattern 2: Multi-System Aggregation

Aggregate across multiple systems:

```python
from app.core.aggregations import MultiSystemAggregator

aggregator = MultiSystemAggregator(HLLMonoid(precision=14))

system_hlls = {
    "production_db": hll_prod,
    "staging_db": hll_staging,
    "api_gateway": hll_api
}

# Total unique users across all systems
total_hll = aggregator.aggregate_systems(system_hlls)
```

### Pattern 3: Distributed Processing

Merge results from parallel workers:

```python
from app.core.aggregations import DistributedAggregator

aggregator = DistributedAggregator(HLLMonoid(precision=14))

# Results from distributed workers
worker_hlls = [worker1_hll, worker2_hll, worker3_hll]

# Merge into final result
final_hll = aggregator.aggregate_workers(worker_hlls)
```

### Pattern 4: Composite Aggregation

Aggregate across **both** time and systems:

```python
from app.core.aggregations import CompositeAggregator

aggregator = CompositeAggregator(HLLMonoid(precision=14))

# Nested structure: {system: {time: HLL}}
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

# Total across everything
total = aggregator.aggregate_time_and_systems(data)

# Per-system daily totals
by_system = aggregator.aggregate_by_system(data)

# Per-hour totals across systems
by_time = aggregator.aggregate_by_time(data)
```

## Redis Storage Integration

The `RedisStorage` class includes Monoid-based aggregation methods:

### Merge HLLs Across Time Windows

```python
from datetime import datetime
from app.core.storage import RedisStorage
from app.utils.time_windows import TimeWindow

storage = RedisStorage()

# Merge 24 hourly HLLs into daily aggregate
hll = storage.merge_hll_time_windows(
    metric="users",
    system="production_db",
    source_window=TimeWindow.HOUR,
    start_time=datetime(2025, 10, 16, 0),
    end_time=datetime(2025, 10, 16, 23),
    precision=14
)
```

### Merge HLLs Across Systems

```python
# Total unique users across all systems
total = storage.merge_hll_systems(
    metric="users",
    systems=["prod", "staging", "api"],
    window=TimeWindow.DAY,
    timestamp=datetime.utcnow()
)
```

### Aggregate TopK Across Windows

```python
# Daily top users from hourly data
top_daily = storage.aggregate_topk_windows(
    metric="active_users",
    system="production_db",
    window=TimeWindow.HOUR,
    start_time=datetime(2025, 10, 16, 0),
    end_time=datetime(2025, 10, 16, 23),
    k=10
)
```

## Comparison: Storm vs Algebird vs PaperTrail Modern

| Feature | Storm (2015) | Twitter Algebird | PaperTrail Modern |
|---------|-------------|------------------|-------------------|
| **Language** | Java | Scala | Python |
| **Abstraction** | Bolts/Topology | Monoids/Semigroups | Monoids (Py) |
| **Composability** | Manual | Built-in | Built-in |
| **HLL Merge** | Custom code | `HLL + HLL` | `monoid.plus(a, b)` |
| **Time Windows** | Complex state | Monoid sum | `sum_time_windows()` |
| **Distributed** | Topology | Monoid merge | `aggregate_workers()` |
| **Memory** | Unbounded | Probabilistic | Probabilistic |

## Examples

See `examples/monoid_examples.py` for comprehensive examples:

1. Hourly → Daily aggregation
2. Multi-system aggregation
3. Bloom filter union
4. TopK merging
5. Running statistics
6. Composite aggregation

Run examples:
```bash
cd papertrail-modern
python examples/monoid_examples.py
```

## Testing

Run Monoid tests:
```bash
pytest tests/test_monoids.py -v
```

## Performance

**Advantages**:
- **O(1) merge cost** for most operations
- **Memory bounded** by data structure size, not data volume
- **Parallel-friendly** - merge results from any number of workers
- **Cache-friendly** - aggregate pre-computed results

**Trade-offs**:
- Approximate results (HLL: ±2%, Bloom: 0.1% false positive)
- Cannot "subtract" or "undo" (monoids are additive)
- Some structures (Bloom) accumulate error on merge

## Further Reading

- [Twitter Algebird](https://github.com/twitter/algebird)
- [HyperLogLog Paper](http://algo.inria.fr/flajolet/Publications/FlFuGaMe07.pdf)
- [Probabilistic Data Structures (datasketch)](https://github.com/ekzhu/datasketch)
- [Monoids, Semigroups, and Categories](https://en.wikipedia.org/wiki/Monoid)
