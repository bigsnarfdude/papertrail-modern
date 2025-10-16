"""
Count-Min Sketch implementation for frequency estimation
Tracks heavy hitters and frequent items with bounded error
"""
import mmh3
from typing import Union, List, Tuple


class CountMinSketch:
    """
    Count-Min Sketch probabilistic data structure for frequency estimation.

    Space: O(w*d) where w=width, d=depth
    Error: ε = e/w (with probability 1-δ, δ=1/e^d)

    Use case: "Which users/IPs have most requests?" without storing all data.
    """

    def __init__(self, width: int = 1000, depth: int = 5):
        """
        Initialize Count-Min Sketch

        Args:
            width: Number of buckets per hash function (larger = more accurate)
            depth: Number of hash functions (larger = higher confidence)

        Typical: width=1000, depth=5 gives ε=0.27% error with 99.3% confidence
        """
        self.width = width
        self.depth = depth
        self.table = [[0] * width for _ in range(depth)]
        self.total_count = 0

    def _get_positions(self, item: Union[str, bytes]) -> List[int]:
        """
        Get positions for item using multiple hash functions

        Args:
            item: Item to hash

        Returns:
            List of positions, one per hash function
        """
        if isinstance(item, str):
            item = item.encode('utf-8')

        positions = []
        for seed in range(self.depth):
            hash_value = mmh3.hash(item, seed=seed, signed=False)
            position = hash_value % self.width
            positions.append(position)

        return positions

    def add(self, item: Union[str, bytes], count: int = 1) -> None:
        """
        Increment count for an item

        Args:
            item: String or bytes to count
            count: Amount to increment (default 1)
        """
        positions = self._get_positions(item)
        for row, col in enumerate(positions):
            self.table[row][col] += count
        self.total_count += count

    def query(self, item: Union[str, bytes]) -> int:
        """
        Estimate frequency of an item

        Args:
            item: String or bytes to query

        Returns:
            Estimated count (always >= true count)
        """
        positions = self._get_positions(item)
        return min(self.table[row][col] for row, col in enumerate(positions))

    def __getitem__(self, item: Union[str, bytes]) -> int:
        """Support bracket notation for queries"""
        return self.query(item)

    def merge(self, other: 'CountMinSketch') -> 'CountMinSketch':
        """
        Merge two Count-Min Sketches

        Args:
            other: Another CountMinSketch

        Returns:
            New CountMinSketch with merged counts
        """
        if self.width != other.width or self.depth != other.depth:
            raise ValueError("Cannot merge sketches with different dimensions")

        merged = CountMinSketch(self.width, self.depth)
        for i in range(self.depth):
            for j in range(self.width):
                merged.table[i][j] = self.table[i][j] + other.table[i][j]
        merged.total_count = self.total_count + other.total_count
        return merged

    def get_heavy_hitters(self, threshold_ratio: float = 0.01) -> List[Tuple[int, float]]:
        """
        Estimate heavy hitters (items above threshold)

        Note: This is an approximation. For exact heavy hitters, use TopK.

        Args:
            threshold_ratio: Minimum frequency ratio (default 1%)

        Returns:
            List of (estimated_count, ratio) tuples
        """
        threshold = self.total_count * threshold_ratio
        heavy_hitters = []

        # Sample from the sketch to find candidates
        for i in range(self.depth):
            for j in range(self.width):
                count = self.table[i][j]
                if count >= threshold:
                    ratio = count / self.total_count if self.total_count > 0 else 0
                    heavy_hitters.append((count, ratio))

        # Sort by count and deduplicate
        heavy_hitters.sort(reverse=True)
        return heavy_hitters[:100]  # Return top 100


class TopK:
    """
    Space-Saving algorithm for tracking Top-K frequent items
    More accurate than Count-Min Sketch for heavy hitters
    """

    def __init__(self, k: int = 100):
        """
        Initialize Top-K tracker

        Args:
            k: Number of top items to track
        """
        self.k = k
        self.items: dict = {}  # item -> count
        self.min_count = 0

    def add(self, item: Union[str, bytes], count: int = 1) -> None:
        """
        Add item to Top-K tracker

        Args:
            item: String or bytes
            count: Amount to increment
        """
        if isinstance(item, bytes):
            item = item.decode('utf-8', errors='ignore')

        if item in self.items:
            # Item already tracked
            self.items[item] += count
        elif len(self.items) < self.k:
            # Still have space
            self.items[item] = count
            if count < self.min_count or self.min_count == 0:
                self.min_count = count
        else:
            # Find and replace minimum if new count is higher
            if count > self.min_count:
                # Remove minimum item
                min_item = min(self.items, key=self.items.get)
                del self.items[min_item]

                # Add new item
                self.items[item] = count
                self.min_count = min(self.items.values())

    def query(self, item: Union[str, bytes]) -> int:
        """Get count for specific item"""
        if isinstance(item, bytes):
            item = item.decode('utf-8', errors='ignore')
        return self.items.get(item, 0)

    def top_k(self, k: int = None) -> List[Tuple[str, int]]:
        """
        Get top K items

        Args:
            k: Number of items to return (default: all tracked items)

        Returns:
            List of (item, count) tuples sorted by count
        """
        k = k or self.k
        sorted_items = sorted(self.items.items(), key=lambda x: x[1], reverse=True)
        return sorted_items[:k]

    def merge(self, other: 'TopK') -> 'TopK':
        """
        Merge two TopK trackers

        Args:
            other: Another TopK tracker

        Returns:
            New TopK with merged data
        """
        merged = TopK(max(self.k, other.k))

        # Add all items from both trackers
        for item, count in self.items.items():
            merged.add(item, count)
        for item, count in other.items.items():
            merged.add(item, count)

        return merged

    def __len__(self) -> int:
        """Return number of tracked items"""
        return len(self.items)

    def __getitem__(self, item: Union[str, bytes]) -> int:
        """Support bracket notation"""
        return self.query(item)


class HeavyHittersDetector:
    """
    Combined Count-Min Sketch + TopK for accurate heavy hitter detection
    Uses CMS for all items, TopK for tracking exact counts of heavy hitters
    """

    def __init__(self, k: int = 100, cms_width: int = 1000, cms_depth: int = 5):
        self.cms = CountMinSketch(cms_width, cms_depth)
        self.topk = TopK(k)
        self.threshold = 0

    def add(self, item: Union[str, bytes], count: int = 1) -> None:
        """Add item and update both structures"""
        self.cms.add(item, count)
        estimated_count = self.cms.query(item)

        # If item is potentially heavy hitter, track in TopK
        if estimated_count > self.threshold:
            self.topk.add(item, count)

            # Update threshold based on current minimum in TopK
            if len(self.topk) >= self.topk.k:
                self.threshold = self.topk.min_count

    def query(self, item: Union[str, bytes]) -> int:
        """Get estimated count for item"""
        # Try TopK first (exact), fall back to CMS (estimated)
        topk_count = self.topk.query(item)
        if topk_count > 0:
            return topk_count
        return self.cms.query(item)

    def get_heavy_hitters(self, k: int = None) -> List[Tuple[str, int]]:
        """Get top K heavy hitters with counts"""
        return self.topk.top_k(k)
