"""
Tests for HyperLogLog implementation
"""
import pytest
from app.core.sketches.hyperloglog import HyperLogLog, HyperLogLogPlus


class TestHyperLogLog:
    """Test HyperLogLog functionality"""

    def test_basic_cardinality(self):
        """Test basic distinct counting"""
        hll = HyperLogLog(precision=14)

        # Add items
        for i in range(1000):
            hll.add(f"user_{i}")

        # Check cardinality (should be ~1000 with ±2% error)
        cardinality = hll.cardinality()
        assert 980 <= cardinality <= 1020, f"Cardinality {cardinality} outside expected range"

    def test_duplicate_handling(self):
        """Test that duplicates don't increase count"""
        hll = HyperLogLog(precision=14)

        # Add same item multiple times
        for _ in range(100):
            hll.add("same_user")

        # Cardinality should be ~1
        cardinality = hll.cardinality()
        assert cardinality == 1, f"Expected 1, got {cardinality}"

    def test_merge_operation(self):
        """Test merging two HLLs"""
        hll1 = HyperLogLog(precision=14)
        hll2 = HyperLogLog(precision=14)

        # Add different items to each
        for i in range(500):
            hll1.add(f"user_{i}")

        for i in range(500, 1000):
            hll2.add(f"user_{i}")

        # Merge
        merged = hll1.merge(hll2)

        # Should have ~1000 unique items
        cardinality = merged.cardinality()
        assert 980 <= cardinality <= 1020, f"Merged cardinality {cardinality} outside range"

    def test_merge_with_overlap(self):
        """Test merging HLLs with overlapping items"""
        hll1 = HyperLogLog(precision=14)
        hll2 = HyperLogLog(precision=14)

        # Add overlapping items
        for i in range(1000):
            hll1.add(f"user_{i}")

        for i in range(500, 1500):
            hll2.add(f"user_{i}")

        # Merge
        merged = hll1.merge(hll2)

        # Should have ~1500 unique items (0-1499)
        cardinality = merged.cardinality()
        assert 1470 <= cardinality <= 1530, f"Merged cardinality {cardinality} outside range"

    def test_serialization(self):
        """Test HLL serialization and deserialization"""
        hll = HyperLogLog(precision=14)

        # Add items
        for i in range(1000):
            hll.add(f"user_{i}")

        original_cardinality = hll.cardinality()

        # Serialize
        data = hll.to_bytes()

        # Deserialize
        restored = HyperLogLog.from_bytes(data, precision=14)
        restored_cardinality = restored.cardinality()

        assert original_cardinality == restored_cardinality

    def test_empty_hll(self):
        """Test empty HLL"""
        hll = HyperLogLog(precision=14)
        assert hll.cardinality() == 0

    def test_large_cardinality(self):
        """Test with large number of items"""
        hll = HyperLogLog(precision=14)

        # Add 100k items
        for i in range(100000):
            hll.add(f"user_{i}")

        # Check cardinality (±2% of 100k = ±2000)
        cardinality = hll.cardinality()
        assert 98000 <= cardinality <= 102000, f"Cardinality {cardinality} outside range"


class TestHyperLogLogPlus:
    """Test HyperLogLog++ (sparse representation)"""

    def test_sparse_mode(self):
        """Test that sparse mode is used for small cardinalities"""
        hll = HyperLogLogPlus(precision=14)

        # Add few items
        for i in range(10):
            hll.add(f"user_{i}")

        # Should still be in sparse mode
        assert hll.is_sparse

        # Cardinality should be exact
        assert hll.cardinality() == 10

    def test_sparse_to_dense_transition(self):
        """Test transition from sparse to dense"""
        hll = HyperLogLogPlus(precision=14)

        # Add many items to trigger transition
        for i in range(1000):
            hll.add(f"user_{i}")

        # Should have transitioned to dense
        assert not hll.is_sparse

        # Cardinality should be approximate
        cardinality = hll.cardinality()
        assert 980 <= cardinality <= 1020


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
