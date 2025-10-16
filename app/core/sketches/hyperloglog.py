"""
HyperLogLog implementation for cardinality estimation
Privacy-preserving distinct count tracking
"""
import mmh3
import math
from typing import Set, Union


class HyperLogLog:
    """
    HyperLogLog probabilistic data structure for cardinality estimation.

    Space: O(m) where m = 2^precision (typically 12-16KB)
    Error: ~1.04/sqrt(m) (typically 0.81%-2% with precision=14)

    Use case: Count distinct users, IPs, sessions without storing raw data.
    """

    def __init__(self, precision: int = 14):
        """
        Initialize HyperLogLog

        Args:
            precision: Number of bits for bucket selection (4-16)
                      Higher = more accurate but more memory
                      14 = ~12KB memory, 0.81% error
        """
        if not 4 <= precision <= 16:
            raise ValueError("Precision must be between 4 and 16")

        self.precision = precision
        self.m = 1 << precision  # 2^precision buckets
        self.registers = [0] * self.m
        self.alpha = self._get_alpha()

    def _get_alpha(self) -> float:
        """Get alpha constant for bias correction"""
        if self.m >= 128:
            return 0.7213 / (1 + 1.079 / self.m)
        elif self.m >= 64:
            return 0.709
        elif self.m >= 32:
            return 0.697
        elif self.m >= 16:
            return 0.673
        else:
            return 0.5

    def add(self, item: Union[str, bytes]) -> None:
        """
        Add an item to the HyperLogLog

        Args:
            item: String or bytes to add
        """
        # Hash the item
        if isinstance(item, str):
            item = item.encode('utf-8')

        hash_value = mmh3.hash(item, signed=False)

        # Use first 'precision' bits for bucket index
        bucket = hash_value & ((1 << self.precision) - 1)

        # Use remaining bits to count leading zeros + 1
        w = hash_value >> self.precision
        leading_zeros = self._leading_zeros(w) + 1

        # Update register with max value
        self.registers[bucket] = max(self.registers[bucket], leading_zeros)

    def _leading_zeros(self, w: int) -> int:
        """Count leading zeros in binary representation"""
        if w == 0:
            return 32 - self.precision

        return (32 - self.precision) - w.bit_length()

    def cardinality(self) -> int:
        """
        Estimate the cardinality (distinct count)

        Returns:
            Estimated number of unique items added
        """
        # Calculate raw estimate
        raw_estimate = self.alpha * (self.m ** 2) / sum(2 ** (-x) for x in self.registers)

        # Apply bias correction for small/large cardinalities
        if raw_estimate <= 2.5 * self.m:
            # Small range correction
            zeros = self.registers.count(0)
            if zeros != 0:
                return int(self.m * math.log(self.m / zeros))

        if raw_estimate <= (1/30) * (1 << 32):
            # No correction needed
            return int(raw_estimate)
        else:
            # Large range correction
            return int(-1 * (1 << 32) * math.log(1 - raw_estimate / (1 << 32)))

    def merge(self, other: 'HyperLogLog') -> 'HyperLogLog':
        """
        Merge two HyperLogLogs (union operation)

        Args:
            other: Another HyperLogLog to merge with

        Returns:
            New HyperLogLog with merged data
        """
        if self.precision != other.precision:
            raise ValueError("Cannot merge HLLs with different precision")

        merged = HyperLogLog(self.precision)
        merged.registers = [
            max(a, b) for a, b in zip(self.registers, other.registers)
        ]
        return merged

    def __len__(self) -> int:
        """Return estimated cardinality"""
        return self.cardinality()

    def __add__(self, other: 'HyperLogLog') -> 'HyperLogLog':
        """Support + operator for merging"""
        return self.merge(other)

    def to_bytes(self) -> bytes:
        """Serialize to bytes for storage"""
        return bytes(self.registers)

    @classmethod
    def from_bytes(cls, data: bytes, precision: int = 14) -> 'HyperLogLog':
        """Deserialize from bytes"""
        hll = cls(precision)
        hll.registers = list(data)
        return hll


class HyperLogLogPlus:
    """
    Enhanced HyperLogLog with sparse representation for small cardinalities
    More memory efficient for low cardinality sets
    """

    def __init__(self, precision: int = 14, sparse_precision: int = 25):
        self.precision = precision
        self.sparse_precision = sparse_precision
        self.sparse: Set[int] = set()
        self.dense: HyperLogLog = None
        self.is_sparse = True

    def add(self, item: Union[str, bytes]) -> None:
        """Add item with sparse/dense mode switching"""
        if self.is_sparse:
            # Hash and encode for sparse representation
            if isinstance(item, str):
                item = item.encode('utf-8')

            hash_value = mmh3.hash(item, signed=False)
            self.sparse.add(hash_value)

            # Switch to dense if sparse set gets too large
            if len(self.sparse) > 6 * self.precision:
                self._to_dense()
        else:
            self.dense.add(item)

    def _to_dense(self) -> None:
        """Convert sparse representation to dense HyperLogLog"""
        self.dense = HyperLogLog(self.precision)
        for hash_value in self.sparse:
            # Reconstruct item representation for HLL
            bucket = hash_value & ((1 << self.precision) - 1)
            w = hash_value >> self.precision
            leading_zeros = self.dense._leading_zeros(w) + 1
            self.dense.registers[bucket] = max(
                self.dense.registers[bucket], leading_zeros
            )
        self.sparse = set()
        self.is_sparse = False

    def cardinality(self) -> int:
        """Get cardinality estimate"""
        if self.is_sparse:
            return len(self.sparse)
        return self.dense.cardinality()

    def __len__(self) -> int:
        return self.cardinality()
