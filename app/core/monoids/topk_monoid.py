"""
TopK Monoid implementation

Enables composable heavy hitters tracking across:
- Time windows (merge hourly top users)
- Systems (combined top users across systems)
- Distributed workers (merge partial top-K results)
"""
from app.core.monoid import Monoid
from app.core.sketches.count_min import TopK


class TopKMonoid(Monoid[TopK]):
    """
    Monoid for TopK heavy hitters

    Example usage:
        # Create monoid
        monoid = TopKMonoid(k=10)

        # Create TopK for different time windows
        topk_morning = monoid.zero()
        topk_morning.add("user1", 100)
        topk_morning.add("user2", 50)

        topk_afternoon = monoid.zero()
        topk_afternoon.add("user2", 75)  # same user
        topk_afternoon.add("user3", 60)

        # Merge to get daily top users
        topk_day = monoid.plus(topk_morning, topk_afternoon)
        # user1: 100, user2: 125, user3: 60
    """

    def __init__(self, k: int = 100):
        """
        Initialize TopKMonoid

        Args:
            k: Number of top items to track
        """
        self.k = k

    def zero(self) -> TopK:
        """
        Identity element: empty TopK

        Returns:
            Empty TopK tracker
        """
        return TopK(k=self.k)

    def plus(self, a: TopK, b: TopK) -> TopK:
        """
        Merge two TopK trackers

        Args:
            a: First TopK
            b: Second TopK

        Returns:
            Merged TopK with combined counts
        """
        return a.merge(b)

    def sum_time_windows(self, topks: list) -> TopK:
        """
        Merge TopK from multiple time windows

        Args:
            topks: List of TopK trackers from different windows

        Returns:
            Combined TopK showing top items across all windows

        Example:
            # Daily top users = merge of hourly tops
            monoid = TopKMonoid(k=10)
            hourly_topks = [topk_00, topk_01, ..., topk_23]
            daily_topk = monoid.sum_time_windows(hourly_topks)
        """
        return self.sum(topks)

    def sum_systems(self, topks: list) -> TopK:
        """
        Merge TopK from multiple systems

        Args:
            topks: List of TopK trackers from different systems

        Returns:
            Combined TopK showing top items across all systems

        Example:
            # Top users across all systems
            monoid = TopKMonoid(k=10)
            system_topks = [topk_prod, topk_staging, topk_api]
            total_topk = monoid.sum_systems(system_topks)
        """
        return self.sum(topks)
