"""
Monoid abstractions inspired by Twitter Algebird

A Monoid is an algebraic structure with:
1. An identity element (zero)
2. An associative binary operation (plus)

This enables:
- Composable aggregations
- Distributed processing
- Time window merging
- Incremental updates
"""
from abc import ABC, abstractmethod
from typing import TypeVar, Generic, List, Optional
from functools import reduce

T = TypeVar('T')


class Monoid(ABC, Generic[T]):
    """
    Abstract Monoid interface

    Laws that implementations must satisfy:
    1. Identity: plus(zero, x) == x and plus(x, zero) == x
    2. Associativity: plus(plus(a, b), c) == plus(a, plus(b, c))
    """

    @abstractmethod
    def zero(self) -> T:
        """
        Identity element

        Returns:
            The zero/identity element for this monoid
        """
        pass

    @abstractmethod
    def plus(self, a: T, b: T) -> T:
        """
        Associative binary operation

        Args:
            a: First element
            b: Second element

        Returns:
            Combined element
        """
        pass

    def sum(self, items: List[T]) -> T:
        """
        Sum a list of elements using the monoid operation

        Args:
            items: List of elements to combine

        Returns:
            Combined result
        """
        if not items:
            return self.zero()
        return reduce(self.plus, items, self.zero())

    def sum_option(self, items: List[Optional[T]]) -> Optional[T]:
        """
        Sum a list of optional elements, skipping None values

        Args:
            items: List of optional elements

        Returns:
            Combined result or None if all inputs are None
        """
        non_none = [item for item in items if item is not None]
        if not non_none:
            return None
        return self.sum(non_none)


class SemigroupLike(ABC, Generic[T]):
    """
    Semigroup: Like a Monoid but without requiring zero/identity
    Useful when identity element is not obvious
    """

    @abstractmethod
    def plus(self, a: T, b: T) -> T:
        """Associative binary operation"""
        pass

    def sum_nonempty(self, items: List[T]) -> Optional[T]:
        """
        Sum non-empty list of elements

        Args:
            items: Non-empty list of elements

        Returns:
            Combined result or None if list is empty
        """
        if not items:
            return None
        return reduce(self.plus, items)


class Ring(Monoid[T]):
    """
    Ring: Extends Monoid with multiplication
    Has two operations: plus (addition) and times (multiplication)
    """

    @abstractmethod
    def one(self) -> T:
        """Multiplicative identity"""
        pass

    @abstractmethod
    def times(self, a: T, b: T) -> T:
        """Multiplication operation"""
        pass

    def product(self, items: List[T]) -> T:
        """Product of elements using multiplication"""
        if not items:
            return self.one()
        return reduce(self.times, items, self.one())


class Group(Monoid[T]):
    """
    Group: Extends Monoid with inverse operation
    Every element has an inverse under plus
    """

    @abstractmethod
    def negate(self, a: T) -> T:
        """
        Inverse operation

        Args:
            a: Element to invert

        Returns:
            Inverse element such that plus(a, negate(a)) == zero
        """
        pass

    def minus(self, a: T, b: T) -> T:
        """
        Subtraction: a - b = a + negate(b)

        Args:
            a: First element
            b: Second element (to subtract)

        Returns:
            Result of subtraction
        """
        return self.plus(a, self.negate(b))


# ============================================================
# Concrete Monoid Implementations for Basic Types
# ============================================================

class IntMonoid(Monoid[int]):
    """Monoid for integers under addition"""

    def zero(self) -> int:
        return 0

    def plus(self, a: int, b: int) -> int:
        return a + b


class FloatMonoid(Monoid[float]):
    """Monoid for floats under addition"""

    def zero(self) -> float:
        return 0.0

    def plus(self, a: float, b: float) -> float:
        return a + b


class StringMonoid(Monoid[str]):
    """Monoid for strings under concatenation"""

    def zero(self) -> str:
        return ""

    def plus(self, a: str, b: str) -> str:
        return a + b


class ListMonoid(Monoid[List[T]]):
    """Monoid for lists under concatenation"""

    def zero(self) -> List[T]:
        return []

    def plus(self, a: List[T], b: List[T]) -> List[T]:
        return a + b


class SetMonoid(Monoid[set]):
    """Monoid for sets under union"""

    def zero(self) -> set:
        return set()

    def plus(self, a: set, b: set) -> set:
        return a | b


class MaxMonoid(Monoid[float]):
    """Monoid for maximum value (uses -inf as identity)"""

    def zero(self) -> float:
        return float('-inf')

    def plus(self, a: float, b: float) -> float:
        return max(a, b)


class MinMonoid(Monoid[float]):
    """Monoid for minimum value (uses +inf as identity)"""

    def zero(self) -> float:
        return float('inf')

    def plus(self, a: float, b: float) -> float:
        return min(a, b)


# ============================================================
# Aggregator: Incremental monoid-based accumulation
# ============================================================

class Aggregator(Generic[T]):
    """
    Algebird-style Aggregator for incremental aggregation

    Combines map, reduce, and present operations into a single abstraction
    """

    def __init__(self, monoid: Monoid[T]):
        self.monoid = monoid
        self.accumulated = monoid.zero()

    def append(self, value: T) -> 'Aggregator[T]':
        """Add a value to the accumulator"""
        self.accumulated = self.monoid.plus(self.accumulated, value)
        return self

    def append_all(self, values: List[T]) -> 'Aggregator[T]':
        """Add multiple values"""
        for value in values:
            self.append(value)
        return self

    def get(self) -> T:
        """Get current accumulated value"""
        return self.accumulated

    def reset(self) -> 'Aggregator[T]':
        """Reset to zero"""
        self.accumulated = self.monoid.zero()
        return self

    def merge(self, other: 'Aggregator[T]') -> 'Aggregator[T]':
        """Merge with another aggregator"""
        self.accumulated = self.monoid.plus(self.accumulated, other.accumulated)
        return self


# ============================================================
# Utility Functions
# ============================================================

def sum_monoid(monoid: Monoid[T], items: List[T]) -> T:
    """
    Convenience function to sum items using a monoid

    Args:
        monoid: Monoid instance
        items: Items to sum

    Returns:
        Combined result
    """
    return monoid.sum(items)


def merge_map(monoid: Monoid[T], maps: List[dict]) -> dict:
    """
    Merge multiple dictionaries using monoid for value combination

    Args:
        monoid: Monoid for combining values
        maps: List of dictionaries to merge

    Returns:
        Merged dictionary
    """
    result = {}
    for m in maps:
        for key, value in m.items():
            if key in result:
                result[key] = monoid.plus(result[key], value)
            else:
                result[key] = value
    return result
