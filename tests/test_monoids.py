"""
Tests for Monoid implementations
"""
import pytest
from app.core.monoid import Monoid, IntMonoid, StringMonoid, MaxMonoid, MinMonoid
from app.core.monoids.hll_monoid import HLLMonoid
from app.core.monoids.bloom_monoid import BloomFilterUnionMonoid
from app.core.monoids.topk_monoid import TopKMonoid
from app.core.monoids.moments_monoid import MomentsMonoid, RunningStatistics
from app.core.sketches.hyperloglog import HyperLogLog
from app.core.sketches.bloom_filter import BloomFilter
from app.core.sketches.count_min import TopK


class TestBasicMonoids:
    """Test basic monoid implementations"""

    def test_int_monoid(self):
        """Test integer addition monoid"""
        monoid = IntMonoid()

        assert monoid.zero() == 0
        assert monoid.plus(5, 3) == 8
        assert monoid.sum([1, 2, 3, 4, 5]) == 15

    def test_string_monoid(self):
        """Test string concatenation monoid"""
        monoid = StringMonoid()

        assert monoid.zero() == ""
        assert monoid.plus("hello", " world") == "hello world"
        assert monoid.sum(["a", "b", "c"]) == "abc"

    def test_max_monoid(self):
        """Test max monoid"""
        monoid = MaxMonoid()

        assert monoid.zero() == float('-inf')
        assert monoid.plus(5, 3) == 5
        assert monoid.sum([1, 5, 3, 9, 2]) == 9

    def test_min_monoid(self):
        """Test min monoid"""
        monoid = MinMonoid()

        assert monoid.zero() == float('inf')
        assert monoid.plus(5, 3) == 3
        assert monoid.sum([5, 1, 9, 2, 7]) == 1


class TestHLLMonoid:
    """Test HyperLogLog Monoid"""

    def test_zero_element(self):
        """Test identity element"""
        monoid = HLLMonoid(precision=14)
        hll_zero = monoid.zero()

        assert hll_zero.cardinality() == 0

    def test_merge_no_overlap(self):
        """Test merging HLLs with no overlap"""
        monoid = HLLMonoid(precision=14)

        # Create two HLLs with different items
        hll1 = monoid.zero()
        for i in range(100):
            hll1.add(f"user_{i}")

        hll2 = monoid.zero()
        for i in range(100, 200):
            hll2.add(f"user_{i}")

        # Merge
        merged = monoid.plus(hll1, hll2)

        # Should have ~200 items
        cardinality = merged.cardinality()
        assert 196 <= cardinality <= 204  # ±2% error

    def test_merge_with_overlap(self):
        """Test merging HLLs with overlapping items"""
        monoid = HLLMonoid(precision=14)

        hll1 = monoid.zero()
        for i in range(150):
            hll1.add(f"user_{i}")

        hll2 = monoid.zero()
        for i in range(50, 200):  # 50-149 overlap
            hll2.add(f"user_{i}")

        # Merge (should deduplicate)
        merged = monoid.plus(hll1, hll2)

        # Should have ~200 unique items (0-199)
        cardinality = merged.cardinality()
        assert 196 <= cardinality <= 204

    def test_sum_time_windows(self):
        """Test merging multiple time windows"""
        monoid = HLLMonoid(precision=14)

        # Simulate 24 hourly HLLs with some overlap
        hourly_hlls = []
        for hour in range(24):
            hll = monoid.zero()
            # Each hour has 50-100 users, with some overlap
            for i in range(hour * 50, hour * 50 + 100):
                hll.add(f"user_{i % 500}")  # Modulo creates overlap
            hourly_hlls.append(hll)

        # Merge into daily
        daily = monoid.sum_time_windows(hourly_hlls)

        # Should have ~500 unique users (due to modulo)
        cardinality = daily.cardinality()
        assert 490 <= cardinality <= 510


class TestBloomFilterMonoid:
    """Test Bloom Filter Monoid"""

    def test_zero_element(self):
        """Test empty Bloom filter"""
        monoid = BloomFilterUnionMonoid(capacity=1000, error_rate=0.001)
        bf_zero = monoid.zero()

        assert "nonexistent" not in bf_zero

    def test_union(self):
        """Test union of Bloom filters"""
        monoid = BloomFilterUnionMonoid(capacity=1000, error_rate=0.001)

        bf1 = monoid.zero()
        bf1.add("user1")
        bf1.add("user2")

        bf2 = monoid.zero()
        bf2.add("user3")
        bf2.add("user4")

        # Union
        bf_union = monoid.plus(bf1, bf2)

        assert "user1" in bf_union
        assert "user2" in bf_union
        assert "user3" in bf_union
        assert "user4" in bf_union

    def test_union_with_overlap(self):
        """Test union with overlapping items"""
        monoid = BloomFilterUnionMonoid(capacity=1000, error_rate=0.001)

        bf1 = monoid.zero()
        bf1.add("user1")
        bf1.add("user2")

        bf2 = monoid.zero()
        bf2.add("user2")  # duplicate
        bf2.add("user3")

        bf_union = monoid.plus(bf1, bf2)

        assert "user1" in bf_union
        assert "user2" in bf_union
        assert "user3" in bf_union


class TestTopKMonoid:
    """Test TopK Monoid"""

    def test_zero_element(self):
        """Test empty TopK"""
        monoid = TopKMonoid(k=10)
        topk_zero = monoid.zero()

        assert len(topk_zero) == 0

    def test_merge_no_overlap(self):
        """Test merging TopK with different users"""
        monoid = TopKMonoid(k=10)

        topk1 = monoid.zero()
        topk1.add("user1", 100)
        topk1.add("user2", 50)

        topk2 = monoid.zero()
        topk2.add("user3", 75)
        topk2.add("user4", 25)

        merged = monoid.plus(topk1, topk2)
        top_items = merged.top_k(10)

        # Should have 4 items
        assert len(top_items) == 4

        # Verify order
        assert top_items[0] == ("user1", 100)
        assert top_items[1] == ("user3", 75)

    def test_merge_with_overlap(self):
        """Test merging TopK with same users (counts add)"""
        monoid = TopKMonoid(k=10)

        topk1 = monoid.zero()
        topk1.add("user1", 100)
        topk1.add("user2", 50)

        topk2 = monoid.zero()
        topk2.add("user1", 50)  # same user
        topk2.add("user3", 75)

        merged = monoid.plus(topk1, topk2)
        top_items = merged.top_k(10)

        # user1 should have 150 total
        assert ("user1", 150) in top_items


class TestMomentsMonoid:
    """Test Moments Monoid for statistics"""

    def test_from_values(self):
        """Test creating moments from values"""
        monoid = MomentsMonoid()
        m = monoid.from_values([1, 2, 3, 4, 5])

        assert m.count == 5
        assert abs(m.mean - 3.0) < 0.01
        assert abs(m.variance - 2.5) < 0.01

    def test_merge_moments(self):
        """Test merging statistical moments"""
        monoid = MomentsMonoid()

        # First batch
        m1 = monoid.from_values([1, 2, 3, 4, 5])

        # Second batch
        m2 = monoid.from_values([6, 7, 8, 9, 10])

        # Merge
        m_total = monoid.plus(m1, m2)

        # Should have combined statistics
        assert m_total.count == 10
        assert abs(m_total.mean - 5.5) < 0.01

    def test_running_statistics(self):
        """Test mutable running statistics"""
        stats = RunningStatistics()

        stats.add_all([1, 2, 3, 4, 5])

        assert stats.count == 5
        assert abs(stats.mean - 3.0) < 0.01
        assert abs(stats.stddev - 1.58) < 0.01

    def test_sum_time_windows(self):
        """Test merging statistics from multiple windows"""
        monoid = MomentsMonoid()

        # Simulate hourly statistics
        hourly_moments = [
            monoid.from_values([100, 110, 120]),  # Hour 1
            monoid.from_values([105, 115, 125]),  # Hour 2
            monoid.from_values([110, 120, 130]),  # Hour 3
        ]

        # Merge into daily
        daily = monoid.sum_time_windows(hourly_moments)

        assert daily.count == 9
        assert 110 < daily.mean < 120


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
