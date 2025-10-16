"""
Moments Monoid for statistical aggregation

Inspired by Twitter Algebird's Moments
Tracks mean, variance, skewness, kurtosis in O(1) space
"""
import math
from typing import NamedTuple
from app.core.monoid import Monoid


class Moments(NamedTuple):
    """
    Statistical moments for a stream of values

    Tracks first 4 central moments:
    - m0: count
    - m1: mean
    - m2: variance (unnormalized)
    - m3: skewness (unnormalized)
    - m4: kurtosis (unnormalized)
    """
    m0: int = 0      # count
    m1: float = 0.0  # mean
    m2: float = 0.0  # variance (unnormalized)
    m3: float = 0.0  # skewness (unnormalized)
    m4: float = 0.0  # kurtosis (unnormalized)

    @property
    def count(self) -> int:
        """Number of observations"""
        return self.m0

    @property
    def mean(self) -> float:
        """Sample mean"""
        return self.m1 if self.m0 > 0 else 0.0

    @property
    def variance(self) -> float:
        """Sample variance"""
        if self.m0 < 2:
            return 0.0
        return self.m2 / self.m0

    @property
    def stddev(self) -> float:
        """Sample standard deviation"""
        return math.sqrt(self.variance)

    @property
    def skewness(self) -> float:
        """Sample skewness (measure of asymmetry)"""
        if self.m0 < 3 or self.m2 == 0:
            return 0.0
        return (self.m3 * self.m0) / (self.m2 ** 1.5)

    @property
    def kurtosis(self) -> float:
        """Sample kurtosis (measure of tailedness)"""
        if self.m0 < 4 or self.m2 == 0:
            return 0.0
        return (self.m4 * self.m0) / (self.m2 ** 2) - 3.0  # Excess kurtosis


class MomentsMonoid(Monoid[Moments]):
    """
    Monoid for statistical moments

    Enables incremental and distributed computation of statistics
    Uses numerically stable algorithms (Welford's method)

    Example usage:
        # Create monoid
        monoid = MomentsMonoid()

        # Stream 1: Morning data
        m1 = monoid.from_values([100, 150, 120, 180])

        # Stream 2: Afternoon data
        m2 = monoid.from_values([140, 160, 130, 170])

        # Merge to get daily statistics
        m_day = monoid.plus(m1, m2)

        print(f"Mean: {m_day.mean:.2f}")
        print(f"StdDev: {m_day.stddev:.2f}")
        print(f"Count: {m_day.count}")
    """

    def zero(self) -> Moments:
        """
        Identity element: no observations

        Returns:
            Empty Moments
        """
        return Moments()

    def plus(self, a: Moments, b: Moments) -> Moments:
        """
        Merge two Moments (numerically stable)

        Uses parallel algorithm for combining moments
        Reference: https://www.johndcook.com/blog/skewness_kurtosis/

        Args:
            a: First Moments
            b: Second Moments

        Returns:
            Combined Moments
        """
        if a.m0 == 0:
            return b
        if b.m0 == 0:
            return a

        n_a, n_b = a.m0, b.m0
        n = n_a + n_b

        delta = b.m1 - a.m1
        delta2 = delta * delta
        delta3 = delta * delta2
        delta4 = delta2 * delta2

        # Combined mean
        m1 = (n_a * a.m1 + n_b * b.m1) / n

        # Combined variance
        m2 = a.m2 + b.m2 + delta2 * n_a * n_b / n

        # Combined skewness
        m3 = (
            a.m3 + b.m3 +
            delta3 * n_a * n_b * (n_a - n_b) / (n * n) +
            3.0 * delta * (n_a * b.m2 - n_b * a.m2) / n
        )

        # Combined kurtosis
        m4 = (
            a.m4 + b.m4 +
            delta4 * n_a * n_b * (n_a * n_a - n_a * n_b + n_b * n_b) / (n * n * n) +
            6.0 * delta2 * (n_a * n_a * b.m2 + n_b * n_b * a.m2) / (n * n) +
            4.0 * delta * (n_a * b.m3 - n_b * a.m3) / n
        )

        return Moments(m0=n, m1=m1, m2=m2, m3=m3, m4=m4)

    def from_value(self, value: float) -> Moments:
        """
        Create Moments from single value

        Args:
            value: Single observation

        Returns:
            Moments containing this value
        """
        return Moments(m0=1, m1=value, m2=0.0, m3=0.0, m4=0.0)

    def from_values(self, values: list) -> Moments:
        """
        Create Moments from list of values

        Args:
            values: List of observations

        Returns:
            Moments computed from all values

        Example:
            monoid = MomentsMonoid()
            m = monoid.from_values([1, 2, 3, 4, 5])
            print(m.mean)  # 3.0
            print(m.variance)  # 2.5
        """
        moments_list = [self.from_value(v) for v in values]
        return self.sum(moments_list)

    def sum_time_windows(self, moments_list: list) -> Moments:
        """
        Merge moments from multiple time windows

        Args:
            moments_list: List of Moments from different windows

        Returns:
            Combined statistics across all windows

        Example:
            # Daily statistics = merge of hourly statistics
            monoid = MomentsMonoid()
            hourly_moments = [m_00, m_01, ..., m_23]
            daily_moments = monoid.sum_time_windows(hourly_moments)
        """
        return self.sum(moments_list)


class RunningStatistics:
    """
    Mutable wrapper around MomentsMonoid for incremental updates

    Convenient for streaming data without creating intermediate Moments
    """

    def __init__(self):
        self.monoid = MomentsMonoid()
        self.moments = self.monoid.zero()

    def add(self, value: float) -> None:
        """Add a single value"""
        new_moment = self.monoid.from_value(value)
        self.moments = self.monoid.plus(self.moments, new_moment)

    def add_all(self, values: list) -> None:
        """Add multiple values"""
        for value in values:
            self.add(value)

    def merge(self, other: 'RunningStatistics') -> None:
        """Merge with another RunningStatistics"""
        self.moments = self.monoid.plus(self.moments, other.moments)

    @property
    def count(self) -> int:
        return self.moments.count

    @property
    def mean(self) -> float:
        return self.moments.mean

    @property
    def variance(self) -> float:
        return self.moments.variance

    @property
    def stddev(self) -> float:
        return self.moments.stddev

    @property
    def skewness(self) -> float:
        return self.moments.skewness

    @property
    def kurtosis(self) -> float:
        return self.moments.kurtosis

    def get_moments(self) -> Moments:
        """Get underlying Moments object"""
        return self.moments
