"""
Bloom Filter Monoid implementation

Enables composable membership testing across:
- Time windows (union of hourly filters)
- Systems (combined activity across systems)
- Distributed workers (merge partial results)
"""
from typing import List
from app.core.monoid import Monoid, SemigroupLike
from app.core.sketches.bloom_filter import BloomFilter


class BloomFilterMonoid(SemigroupLike[BloomFilter]):
    """
    Semigroup (not full Monoid) for Bloom Filters

    Note: Bloom filters don't have a true "zero" element in practice,
    since an empty filter with different capacity/error_rate parameters
    cannot be meaningfully merged. Therefore, we use Semigroup instead.

    Operations:
    - union: Combine two filters (OR operation)
    - intersection: Find common elements (AND operation)

    Example usage:
        # Create semigroup
        semigroup = BloomFilterMonoid()

        # Create filters for different time windows
        bf_morning = BloomFilter(capacity=100000)
        bf_morning.add("user1")
        bf_morning.add("user2")

        bf_afternoon = BloomFilter(capacity=100000)
        bf_afternoon.add("user2")  # duplicate
        bf_afternoon.add("user3")

        # Union: users active in either window
        bf_day = semigroup.plus(bf_morning, bf_afternoon)
        print("user2" in bf_day)  # True
    """

    def plus(self, a: BloomFilter, b: BloomFilter) -> BloomFilter:
        """
        Union of two Bloom filters (OR operation)

        Args:
            a: First Bloom filter
            b: Second Bloom filter

        Returns:
            New Bloom filter containing union

        Raises:
            ValueError: If filters have incompatible parameters
        """
        return a.union(b)

    def intersection(self, a: BloomFilter, b: BloomFilter) -> BloomFilter:
        """
        Intersection of two Bloom filters (AND operation)

        Note: This can increase false positive rate!

        Args:
            a: First Bloom filter
            b: Second Bloom filter

        Returns:
            New Bloom filter containing intersection
        """
        return a.intersection(b)

    def sum_union(self, filters: List[BloomFilter]) -> BloomFilter:
        """
        Union of multiple Bloom filters

        Args:
            filters: List of Bloom filters

        Returns:
            Combined filter (OR of all inputs)

        Example:
            # Activity across all time windows
            hourly_filters = [bf_00, bf_01, ..., bf_23]
            daily_filter = semigroup.sum_union(hourly_filters)
        """
        result = self.sum_nonempty(filters)
        if result is None:
            raise ValueError("Cannot union empty list of Bloom filters")
        return result


class BloomFilterUnionMonoid(Monoid[BloomFilter]):
    """
    Full Monoid for Bloom Filter union with fixed parameters

    This requires all filters to have same capacity and error_rate,
    allowing us to define a proper zero element.
    """

    def __init__(self, capacity: int = 1_000_000, error_rate: float = 0.001):
        """
        Initialize with fixed Bloom filter parameters

        Args:
            capacity: Fixed capacity for all filters
            error_rate: Fixed error rate for all filters
        """
        self.capacity = capacity
        self.error_rate = error_rate

    def zero(self) -> BloomFilter:
        """
        Identity element: empty Bloom filter

        Returns:
            Empty Bloom filter with specified parameters
        """
        return BloomFilter(capacity=self.capacity, error_rate=self.error_rate)

    def plus(self, a: BloomFilter, b: BloomFilter) -> BloomFilter:
        """
        Union operation

        Args:
            a: First filter
            b: Second filter

        Returns:
            Union of both filters
        """
        return a.union(b)

    def sum_time_windows(self, filters: List[BloomFilter]) -> BloomFilter:
        """
        Merge filters from multiple time windows

        Args:
            filters: List of Bloom filters from different windows

        Returns:
            Combined filter showing activity across all windows

        Example:
            # Daily activity = union of hourly activity
            monoid = BloomFilterUnionMonoid()
            hourly = [bf_00, bf_01, ..., bf_23]
            daily = monoid.sum_time_windows(hourly)
        """
        return self.sum(filters)


class BloomFilterIntersectionMonoid(Monoid[BloomFilter]):
    """
    Monoid for Bloom Filter intersection

    Note: Intersection increases false positive rate!
    Use with caution.
    """

    def __init__(self, capacity: int = 1_000_000, error_rate: float = 0.001):
        self.capacity = capacity
        self.error_rate = error_rate

    def zero(self) -> BloomFilter:
        """
        Identity element: full filter (all bits set)

        For intersection, identity is the "everything" element
        """
        bf = BloomFilter(capacity=self.capacity, error_rate=self.error_rate)
        # Set all bits to 1
        bf.bit_array = bytearray([0xFF] * len(bf.bit_array))
        return bf

    def plus(self, a: BloomFilter, b: BloomFilter) -> BloomFilter:
        """
        Intersection operation

        Args:
            a: First filter
            b: Second filter

        Returns:
            Intersection of both filters
        """
        return a.intersection(b)

    def find_common(self, filters: List[BloomFilter]) -> BloomFilter:
        """
        Find items present in ALL filters

        Args:
            filters: List of filters

        Returns:
            Filter containing only common elements

        Example:
            # Users active in ALL systems
            monoid = BloomFilterIntersectionMonoid()
            system_filters = [bf_prod, bf_staging, bf_api]
            common = monoid.find_common(system_filters)
        """
        return self.sum(filters)
