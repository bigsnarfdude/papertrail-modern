"""
Monoid abstractions inspired by Twitter Algebird - Now powered by algesnake!

A Monoid is an algebraic structure with:
1. An identity element (zero)
2. An associative binary operation (plus)

This enables:
- Composable aggregations
- Distributed processing
- Time window merging
- Incremental updates

MIGRATION NOTE: This module now uses algesnake library for improved performance
and better API ergonomics while maintaining backward compatibility.
"""
from typing import TypeVar, Generic, List, Optional
from functools import reduce

# Import algesnake abstract classes
from algesnake.abstract import Monoid as AlgesnakeMonoid
from algesnake.abstract import Semigroup as AlgessnakeSemigroup
from algesnake.abstract import Group as AlgesnakeGroup
from algesnake.abstract import Ring as AlgesnakeRing

# Import concrete monoid implementations from algesnake
from algesnake import Add, Multiply, Max, Min
from algesnake import SetMonoid, ListMonoid, StringMonoid

T = TypeVar('T')


# ============================================================
# Compatibility Layer: Maintain backward compatibility
# ============================================================

class Monoid(AlgesnakeMonoid[T]):
    """
    Monoid interface - now powered by algesnake

    This class extends algesnake's Monoid to maintain backward compatibility
    with existing code while providing access to algesnake's optimized implementations.

    Laws that implementations must satisfy:
    1. Identity: plus(zero, x) == x and plus(x, zero) == x
    2. Associativity: plus(plus(a, b), c) == plus(a, plus(b, c))
    """

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


class SemigroupLike(AlgessnakeSemigroup[T]):
    """
    Semigroup: Like a Monoid but without requiring zero/identity
    Useful when identity element is not obvious

    Now powered by algesnake!
    """

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


class Ring(AlgesnakeRing[T]):
    """
    Ring: Extends Monoid with multiplication
    Has two operations: plus (addition) and times (multiplication)

    Now powered by algesnake!
    """
    pass


class Group(AlgesnakeGroup[T]):
    """
    Group: Extends Monoid with inverse operation
    Every element has an inverse under plus

    Now powered by algesnake!
    """

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
# Concrete Monoid Implementations - Using algesnake
# ============================================================

# Re-export algesnake monoids with backward-compatible names
IntMonoid = Add  # algesnake's Add monoid for integers
FloatMonoid = Add  # algesnake's Add also works for floats

# algesnake's concrete implementations are already optimal
MaxMonoid = Max  # algesnake's Max monoid
MinMonoid = Min  # algesnake's Min monoid

# Note: StringMonoid, ListMonoid, SetMonoid are already imported from algesnake above


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
