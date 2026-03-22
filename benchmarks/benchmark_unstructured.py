"""Benchmark script for unstructured anonymization and de-anonymization."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import httpx
import psutil


DEFAULT_OUTPUT = Path("data/benchmark_results/unstructured_benchmark_results.json")


@dataclass
class TextScenario:
    """A benchmark text scenario."""

    name: str
    description: str
    template: str
    repeat: int = 1

    def build(self, index: int) -> str:
        """Build a scenario text instance."""
        text = self.template.format(
            idx=index,
            person=f"Γιάννης Παπαδόπουλος {index}",
            company=f"Acme Hellas {index}",
            city="Αθήνα",
            email=f"user{index}@example.com",
            phone=f"691{index % 10}{(index * 1111111) % 10000000:07d}",
            afm=f"{100000000 + (index % 899999999)}",
            amka=f"{10000000000 + index:011d}"[-11:],
        )
        return " ".join([text] * self.repeat)


@dataclass
class ScenarioResult:
    """Benchmark metrics for a single scenario."""

    scenario: str
    operation: str
    total_requests: int
    avg_chars: float
    execution_time_seconds: float
    throughput_requests_per_sec: float
    throughput_chars_per_sec: float
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    memory_usage_mb: float
    cpu_utilization_percent: float
    errors: int
    sla_throughput_target: float | None
    sla_p95_target_ms: float | None
    sla_throughput_pass: bool | None
    sla_p95_pass: bool | None


class UnstructuredBenchmark:
    """REST benchmark harness for unstructured endpoints."""

    def __init__(
        self,
        base_url: str,
        system_id: str,
        api_key: str | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.system_id = system_id
        self.api_key = api_key
        self.client = httpx.AsyncClient(timeout=timeout_seconds)

    def _headers(self) -> dict[str, str]:
        headers = {
            "X-System-ID": self.system_id,
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def check_health(self) -> None:
        """Validate that the service is reachable."""
        response = await self.client.get(f"{self.base_url}/health")
        response.raise_for_status()

    async def anonymize_text(self, text: str) -> tuple[float, dict[str, Any] | None]:
        """Call unstructured anonymize endpoint."""
        start = time.perf_counter()
        try:
            response = await self.client.post(
                f"{self.base_url}/unstructured/anonymize",
                json={"text": text, "return_entity_map": False},
                headers=self._headers(),
            )
            response.raise_for_status()
            elapsed_ms = (time.perf_counter() - start) * 1000
            return elapsed_ms, response.json()
        except Exception:
            return -1.0, None

    async def deanonymize_text(self, text: str) -> tuple[float, dict[str, Any] | None]:
        """Call unstructured deanonymize endpoint."""
        start = time.perf_counter()
        try:
            response = await self.client.post(
                f"{self.base_url}/unstructured/deanonymize",
                json={"text": text},
                headers=self._headers(),
            )
            response.raise_for_status()
            elapsed_ms = (time.perf_counter() - start) * 1000
            return elapsed_ms, response.json()
        except Exception:
            return -1.0, None

    async def run_scenario(
        self,
        scenario: TextScenario,
        total_requests: int,
        concurrency: int,
        benchmark_deanonymize: bool,
        throughput_target: float | None,
        p95_target_ms: float | None,
    ) -> list[ScenarioResult]:
        """Run anonymization and optional deanonymization for a scenario."""
        texts = [scenario.build(i) for i in range(total_requests)]
        avg_chars = statistics.mean(len(text) for text in texts) if texts else 0.0
        results = [
            await self._run_operation(
                scenario_name=scenario.name,
                operation="anonymize",
                texts=texts,
                concurrency=concurrency,
                call=self.anonymize_text,
                throughput_target=throughput_target,
                p95_target_ms=p95_target_ms,
                transform_output=lambda payload: payload["anonymized_text"] if payload else None,
            )
        ]

        if benchmark_deanonymize:
            anonymized_texts = await self._collect_anonymized_texts(texts, concurrency)
            results.append(
                await self._run_operation(
                    scenario_name=scenario.name,
                    operation="deanonymize",
                    texts=anonymized_texts,
                    concurrency=concurrency,
                    call=self.deanonymize_text,
                    throughput_target=None,
                    p95_target_ms=p95_target_ms,
                    transform_output=lambda payload: payload["text"] if payload else None,
                )
            )

        for result in results:
            result.avg_chars = avg_chars

        return results

    async def _collect_anonymized_texts(self, texts: list[str], concurrency: int) -> list[str]:
        """Generate anonymized texts for de-anonymization benchmark setup."""
        semaphore = asyncio.Semaphore(concurrency)
        anonymized: list[str] = []

        async def work(text: str) -> None:
            async with semaphore:
                _latency, payload = await self.anonymize_text(text)
                if payload is not None:
                    anonymized.append(payload["anonymized_text"])

        await asyncio.gather(*(work(text) for text in texts))
        return anonymized

    async def _run_operation(
        self,
        scenario_name: str,
        operation: str,
        texts: list[str],
        concurrency: int,
        call,
        throughput_target: float | None,
        p95_target_ms: float | None,
        transform_output,
    ) -> ScenarioResult:
        """Execute a benchmark operation with concurrency control."""
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024
        process.cpu_percent()
        await asyncio.sleep(0.05)

        semaphore = asyncio.Semaphore(concurrency)
        latencies: list[float] = []
        output_chars = 0
        errors = 0

        start = time.perf_counter()

        async def work(text: str) -> None:
            nonlocal output_chars, errors
            async with semaphore:
                latency_ms, payload = await call(text)
                if latency_ms < 0 or payload is None:
                    errors += 1
                    return
                latencies.append(latency_ms)
                output_text = transform_output(payload)
                if output_text:
                    output_chars += len(output_text)

        await asyncio.gather(*(work(text) for text in texts))
        execution_time = time.perf_counter() - start
        cpu_utilization = process.cpu_percent()
        final_memory = process.memory_info().rss / 1024 / 1024

        success_count = max(len(texts) - errors, 0)
        throughput_requests = success_count / execution_time if execution_time else 0.0
        throughput_chars = output_chars / execution_time if execution_time else 0.0
        p50 = percentile(latencies, 0.50)
        p95 = percentile(latencies, 0.95)
        p99 = percentile(latencies, 0.99)

        return ScenarioResult(
            scenario=scenario_name,
            operation=operation,
            total_requests=success_count,
            avg_chars=0.0,
            execution_time_seconds=execution_time,
            throughput_requests_per_sec=throughput_requests,
            throughput_chars_per_sec=throughput_chars,
            latency_p50_ms=p50,
            latency_p95_ms=p95,
            latency_p99_ms=p99,
            memory_usage_mb=max(final_memory - initial_memory, 0.0),
            cpu_utilization_percent=cpu_utilization,
            errors=errors,
            sla_throughput_target=throughput_target,
            sla_p95_target_ms=p95_target_ms,
            sla_throughput_pass=(
                throughput_requests >= throughput_target if throughput_target is not None else None
            ),
            sla_p95_pass=(p95 <= p95_target_ms if p95_target_ms is not None else None),
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()


def percentile(samples: Iterable[float], p: float) -> float:
    """Compute percentile from a sequence of samples."""
    values = sorted(samples)
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    rank = (len(values) - 1) * p
    lower = int(rank)
    upper = min(lower + 1, len(values) - 1)
    weight = rank - lower
    return values[lower] + weight * (values[upper] - values[lower])


def default_scenarios() -> list[TextScenario]:
    """Return default text scenarios for unstructured benchmarks."""
    return [
        TextScenario(
            name="strict_identifiers_short",
            description="Mostly deterministic PII in short text",
            template=(
                "Παρακαλώ επικοινώνησε με τον πελάτη στο {email} ή στο {phone}. "
                "ΑΦΜ: {afm}. ΑΜΚΑ: {amka}."
            ),
        ),
        TextScenario(
            name="mixed_pii_medium",
            description="Mixed semantic and deterministic PII in medium text",
            template=(
                "Ο/Η {person} από την {company} ταξιδεύει στην {city}. "
                "Email επικοινωνίας: {email}. Τηλέφωνο: {phone}. "
                "Το ΑΦΜ του λογαριασμού είναι {afm}."
            ),
            repeat=4,
        ),
        TextScenario(
            name="mixed_pii_long",
            description="Longer narrative text with repeated PII markers",
            template=(
                "Σημείωση υπόθεσης {idx}: Ο/Η {person} συνεργάζεται με την {company} "
                "και βρίσκεται στην {city}. Για συνέχεια χρησιμοποίησε {email} και {phone}. "
                "ΑΦΜ {afm}, ΑΜΚΑ {amka}. Η περιγραφή της περίπτωσης περιλαμβάνει πολλαπλές "
                "αναφορές στο ίδιο πρόσωπο και στα ίδια identifiers."
            ),
            repeat=12,
        ),
        TextScenario(
            name="control_no_pii",
            description="Control scenario with clean text",
            template=(
                "Αυτό είναι λειτουργικό μήνυμα χωρίς προσωπικά δεδομένα. "
                "Το σύστημα επεξεργάζεται αίτημα {idx} και επιστρέφει τεχνική ενημέρωση."
            ),
            repeat=6,
        ),
    ]


def print_summary(results: list[ScenarioResult]) -> None:
    """Print a concise SLA-focused summary."""
    print("\n" + "=" * 72)
    print("UNSTRUCTURED BENCHMARK RESULTS")
    print("=" * 72)
    for result in results:
        throughput_status = format_sla(result.sla_throughput_pass)
        latency_status = format_sla(result.sla_p95_pass)
        print(
            f"{result.scenario}/{result.operation}: "
            f"{result.throughput_requests_per_sec:,.1f} req/s, "
            f"p95 {result.latency_p95_ms:.2f} ms, "
            f"errors {result.errors}, "
            f"throughput SLA {throughput_status}, latency SLA {latency_status}"
        )
    print("=" * 72)


def format_sla(value: bool | None) -> str:
    """Render SLA state."""
    if value is None:
        return "n/a"
    return "pass" if value else "fail"


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run unstructured REST benchmarks")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--system-id", default="customer_db")
    parser.add_argument("--api-key", default="test_key")
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--throughput-sla", type=float, default=200.0)
    parser.add_argument("--p95-sla-ms", type=float, default=150.0)
    parser.add_argument("--skip-deanonymize", action="store_true")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    benchmark = UnstructuredBenchmark(
        base_url=args.base_url,
        system_id=args.system_id,
        api_key=args.api_key,
    )

    try:
        print("Checking service health...")
        await benchmark.check_health()

        all_results: list[ScenarioResult] = []
        for scenario in default_scenarios():
            print(f"Running scenario: {scenario.name}")
            scenario_results = await benchmark.run_scenario(
                scenario=scenario,
                total_requests=args.requests,
                concurrency=args.concurrency,
                benchmark_deanonymize=not args.skip_deanonymize,
                throughput_target=args.throughput_sla,
                p95_target_ms=args.p95_sla_ms,
            )
            all_results.extend(scenario_results)

        print_summary(all_results)

        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "benchmark_type": "unstructured_rest",
            "base_url": args.base_url,
            "system_id": args.system_id,
            "generated_at_unix": time.time(),
            "requests_per_scenario": args.requests,
            "concurrency": args.concurrency,
            "results": [asdict(result) for result in all_results],
        }
        output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Saved results to {output_path}")
    finally:
        await benchmark.close()


if __name__ == "__main__":
    asyncio.run(main())
