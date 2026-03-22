"""Base interface for unstructured PII detectors."""

from abc import ABC, abstractmethod
from typing import List

from ...models.entity import DetectionFinding
from ...models.policy import UnstructuredConfig


class PIIDetector(ABC):
    """Interface for detector backends."""

    requires_network: bool = False

    @abstractmethod
    async def detect(self, text: str, config: UnstructuredConfig) -> List[DetectionFinding]:
        """Detect PII findings in text."""
