"""Deterministic recognizers for format-bound identifiers."""

import re
from typing import Dict, List, Pattern

from ...models.entity import DetectionFinding
from ...models.policy import UnstructuredConfig
from .base import PIIDetector


class DeterministicDetector(PIIDetector):
    """Fast pattern-based detector for strict identifier formats."""

    PATTERNS: Dict[str, Pattern[str]] = {
        "EMAIL": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
        "PHONE_GR": re.compile(
            r"(?<!\w)(?:\+30\s?)?(?:2\d{9}|69\d{8})(?!\w)"
        ),
        "IBAN_GR": re.compile(r"\bGR\d{2}(?:\s?\d{4}){5}\s?\d{3}\b", re.IGNORECASE),
        "AFM_GR": re.compile(r"(?<!\d)\d{9}(?!\d)"),
        "AMKA_GR": re.compile(r"(?<!\d)\d{11}(?!\d)"),
        "UUID": re.compile(
            r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
            re.IGNORECASE,
        ),
        "IP": re.compile(
            r"\b(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}\b"
        ),
    }

    async def detect(self, text: str, config: UnstructuredConfig) -> List[DetectionFinding]:
        """Run deterministic recognizers for entities that request them."""
        findings: List[DetectionFinding] = []
        entity_rules = {
            rule.type: rule for rule in config.entities if "deterministic" in rule.detection
        }

        for entity_type, rule in entity_rules.items():
            pattern = self.PATTERNS.get(entity_type)
            if pattern is None:
                continue

            for match in pattern.finditer(text):
                findings.append(
                    DetectionFinding(
                        type=entity_type,
                        value=match.group(0),
                        start=match.start(),
                        end=match.end(),
                        detector="deterministic",
                        confidence=1.0,
                        action=rule.action,
                    )
                )

        return findings
