"""
Bloom Filter implementation for set membership queries
Fast probabilistic "has this been seen before?" checks
"""
import mmh3
import math
from typing import Union


class BloomFilter:
    """
    Bloom Filter probabilistic data structure for membership testing.

    Space: O(n*k) bits where n=capacity, k=hash functions
    False Positive Rate: (1 - e^(-kn/m))^k
    False Negative Rate: 0 (never happens)

    Use case: "Did user X access system Y?" with minimal memory.
    """

    def __init__(self, capacity: int = 1_000_000, error_rate: float = 0.001):
        """
        Initialize Bloom Filter

        Args:
            capacity: Expected number of items
            error_rate: Desired false positive rate (0.001 = 0.1%)
        """
        self.capacity = capacity
        self.error_rate = error_rate

        # Calculate optimal bit array size and hash function count
        self.bit_size = self._optimal_bit_size(capacity, error_rate)
        self.hash_count = self._optimal_hash_count(self.bit_size, capacity)

        # Initialize bit array
        self.bit_array = bytearray(math.ceil(self.bit_size / 8))

    @staticmethod
    def _optimal_bit_size(n: int, p: float) -> int:
        """
        Calculate optimal bit array size

        m = -n*ln(p) / (ln(2)^2)
        """
        return int(-n * math.log(p) / (math.log(2) ** 2))

    @staticmethod
    def _optimal_hash_count(m: int, n: int) -> int:
        """
        Calculate optimal number of hash functions

        k = (m/n) * ln(2)
        """
        return max(1, int((m / n) * math.log(2)))

    def _get_positions(self, item: Union[str, bytes]) -> list:
        """
        Get bit positions for an item using multiple hash functions

        Args:
            item: Item to hash

        Returns:
            List of bit positions
        """
        if isinstance(item, str):
            item = item.encode('utf-8')

        positions = []
        for seed in range(self.hash_count):
            hash_value = mmh3.hash(item, seed=seed, signed=False)
            position = hash_value % self.bit_size
            positions.append(position)

        return positions

    def add(self, item: Union[str, bytes]) -> None:
        """
        Add an item to the Bloom filter

        Args:
            item: String or bytes to add
        """
        for position in self._get_positions(item):
            byte_index = position // 8
            bit_index = position % 8
            self.bit_array[byte_index] |= (1 << bit_index)

    def contains(self, item: Union[str, bytes]) -> bool:
        """
        Check if item might be in the set

        Args:
            item: String or bytes to check

        Returns:
            True: Item might be in set (or false positive)
            False: Item definitely NOT in set
        """
        for position in self._get_positions(item):
            byte_index = position // 8
            bit_index = position % 8
            if not (self.bit_array[byte_index] & (1 << bit_index)):
                return False
        return True

    def __contains__(self, item: Union[str, bytes]) -> bool:
        """Support 'in' operator"""
        return self.contains(item)

    def estimated_fill_ratio(self) -> float:
        """Calculate estimated fill ratio of bit array"""
        set_bits = sum(bin(byte).count('1') for byte in self.bit_array)
        return set_bits / self.bit_size

    def estimated_count(self) -> int:
        """
        Estimate number of items added

        n ≈ -m/k * ln(1 - X/m)
        where X is number of set bits
        """
        set_bits = sum(bin(byte).count('1') for byte in self.bit_array)
        if set_bits == 0:
            return 0

        fill_ratio = set_bits / self.bit_size
        if fill_ratio >= 1.0:
            return self.capacity

        return int(
            -self.bit_size / self.hash_count * math.log(1 - fill_ratio)
        )

    def current_error_rate(self) -> float:
        """
        Calculate current false positive rate

        FPR = (1 - e^(-kn/m))^k
        """
        n = self.estimated_count()
        if n == 0:
            return 0.0

        return (1 - math.exp(-self.hash_count * n / self.bit_size)) ** self.hash_count

    def union(self, other: 'BloomFilter') -> 'BloomFilter':
        """
        Union of two Bloom filters (OR operation)

        Args:
            other: Another Bloom filter

        Returns:
            New Bloom filter containing union
        """
        if self.bit_size != other.bit_size or self.hash_count != other.hash_count:
            raise ValueError("Bloom filters must have same parameters for union")

        result = BloomFilter(self.capacity, self.error_rate)
        result.bit_size = self.bit_size
        result.hash_count = self.hash_count
        result.bit_array = bytearray(
            a | b for a, b in zip(self.bit_array, other.bit_array)
        )
        return result

    def intersection(self, other: 'BloomFilter') -> 'BloomFilter':
        """
        Intersection of two Bloom filters (AND operation)

        Args:
            other: Another Bloom filter

        Returns:
            New Bloom filter containing intersection
        """
        if self.bit_size != other.bit_size or self.hash_count != other.hash_count:
            raise ValueError("Bloom filters must have same parameters for intersection")

        result = BloomFilter(self.capacity, self.error_rate)
        result.bit_size = self.bit_size
        result.hash_count = self.hash_count
        result.bit_array = bytearray(
            a & b for a, b in zip(self.bit_array, other.bit_array)
        )
        return result

    def to_bytes(self) -> bytes:
        """Serialize to bytes for storage"""
        return bytes(self.bit_array)

    @classmethod
    def from_bytes(cls, data: bytes, capacity: int, error_rate: float) -> 'BloomFilter':
        """Deserialize from bytes"""
        bf = cls(capacity, error_rate)
        bf.bit_array = bytearray(data)
        return bf

    def __len__(self) -> int:
        """Return estimated item count"""
        return self.estimated_count()


class ScalableBloomFilter:
    """
    Scalable Bloom Filter that grows as needed
    Maintains target error rate as more items are added
    """

    def __init__(self, initial_capacity: int = 1000, error_rate: float = 0.001, growth_rate: int = 2):
        self.initial_capacity = initial_capacity
        self.error_rate = error_rate
        self.growth_rate = growth_rate
        self.filters: list[BloomFilter] = []
        self.current_capacity = initial_capacity
        self._add_filter()

    def _add_filter(self) -> None:
        """Add a new Bloom filter to the chain"""
        # Tighten error rate for each new filter
        error_rate = self.error_rate * (0.5 ** len(self.filters))
        new_filter = BloomFilter(self.current_capacity, error_rate)
        self.filters.append(new_filter)
        self.current_capacity *= self.growth_rate

    def add(self, item: Union[str, bytes]) -> None:
        """Add item, growing capacity if needed"""
        current_filter = self.filters[-1]

        # Check if current filter is too full
        if current_filter.estimated_fill_ratio() > 0.5:
            self._add_filter()
            current_filter = self.filters[-1]

        current_filter.add(item)

    def contains(self, item: Union[str, bytes]) -> bool:
        """Check if item exists in any filter"""
        return any(f.contains(item) for f in self.filters)

    def __contains__(self, item: Union[str, bytes]) -> bool:
        return self.contains(item)

    def estimated_count(self) -> int:
        """Estimate total items across all filters"""
        return sum(f.estimated_count() for f in self.filters)
