"""Greek NER detector based on Hugging Face token classification models."""

from typing import Dict, List

from ...models.entity import DetectionFinding
from ...models.policy import UnstructuredConfig
from .base import PIIDetector


class GreekNERDetector(PIIDetector):
    """Optional local semantic detector for Greek entities."""

    LABEL_MAPPING: Dict[str, str] = {
        "PER": "PERSON",
        "PERSON": "PERSON",
        "ORG": "ORG",
        "GPE": "LOCATION",
        "LOC": "LOCATION",
    }

    def __init__(self) -> None:
        self._pipeline = None
        self._loaded_model = None

    def _ensure_pipeline(self, model_name: str):
        """Lazy-load the HF pipeline only when a semantic policy enables it."""
        if self._pipeline is not None and self._loaded_model == model_name:
            return self._pipeline

        try:
            from transformers import pipeline
        except ImportError as exc:
            raise RuntimeError(
                "Semantic detector requested but 'transformers' is not installed"
            ) from exc

        self._pipeline = pipeline(
            "token-classification",
            model=model_name,
            tokenizer=model_name,
            aggregation_strategy="simple",
        )
        self._loaded_model = model_name
        return self._pipeline

    async def detect(self, text: str, config: UnstructuredConfig) -> List[DetectionFinding]:
        """Run semantic detection when policy enables a Greek NER model."""
        semantic_config = config.semantic_detector
        if semantic_config is None or not semantic_config.enabled_for:
            return []

        model_name = semantic_config.model or "amichailidis/bert-base-greek-uncased-v1-finetuned-ner"
        pipeline = self._ensure_pipeline(model_name)
        raw_entities = pipeline(text)
        allowed_types = set(semantic_config.enabled_for)
        entity_rules = {
            rule.type: rule for rule in config.entities if "semantic" in rule.detection
        }
        findings: List[DetectionFinding] = []

        for entity in raw_entities:
            raw_label = entity.get("entity_group") or entity.get("entity")
            canonical_label = self.LABEL_MAPPING.get(raw_label, raw_label)
            if canonical_label not in allowed_types:
                continue

            score = float(entity.get("score", 0.0))
            rule = entity_rules.get(canonical_label)
            threshold = (
                rule.min_confidence
                if rule and rule.min_confidence is not None
                else semantic_config.threshold
            )
            if score < threshold:
                continue

            findings.append(
                DetectionFinding(
                    type=canonical_label,
                    value=entity["word"],
                    start=int(entity["start"]),
                    end=int(entity["end"]),
                    detector="semantic",
                    confidence=score,
                    action=rule.action if rule else "tokenize",
                )
            )

        return findings
