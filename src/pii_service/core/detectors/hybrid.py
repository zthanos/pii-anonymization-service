"""Hybrid detector that combines deterministic and semantic stages."""

from typing import List

from ...models.entity import DetectionFinding
from ...models.policy import UnstructuredConfig
from .base import PIIDetector


class HybridDetector(PIIDetector):
    """Detector pipeline with prefilter, deterministic, and semantic stages."""

    def __init__(
        self,
        deterministic_detector: PIIDetector,
        semantic_detector: PIIDetector | None = None,
    ):
        self.deterministic_detector = deterministic_detector
        self.semantic_detector = semantic_detector
        self.requires_network = False

    async def detect(self, text: str, config: UnstructuredConfig) -> List[DetectionFinding]:
        """Run the configured detector stages."""
        if config.prefilter.enabled and len(text.strip()) < config.prefilter.min_length:
            return []

        findings: List[DetectionFinding] = []

        deterministic_needed = any(
            "deterministic" in rule.detection for rule in config.entities
        )
        if deterministic_needed:
            findings.extend(await self.deterministic_detector.detect(text, config))

        semantic_needed = any("semantic" in rule.detection for rule in config.entities)
        if semantic_needed and self.semantic_detector is not None:
            findings.extend(await self.semantic_detector.detect(text, config))

        return findings
