"""Base collector interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.models import RawProduct


class BaseCollector(ABC):
    """Abstract base for all data collectors."""

    @abstractmethod
    async def collect(self, category: str, limit: int = 20) -> list[RawProduct]:
        """Collect products from the source."""
        ...
