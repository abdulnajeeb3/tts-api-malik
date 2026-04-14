"""Benchmark the API-level TTS models currently exposed by the server.

Usage (from repo root, inside the container or venv):

    python -m benchmark.run_benchmark \\
        --base-url http://localhost:8000 \\
        --api-key dev-local-key-change-me \\
        --output-dir benchmark/output

What it does:
    For each phrase in test_phrases.txt, send a REST request to each enabled
    model, record TTFA/total_ms/audio_duration/RTF, save the audio as WAV,
    and print a summary table at the end.

Real-time factor (RTF):
    RTF = generation_time / audio_duration
    RTF < 1.0  =>  faster than real time (good)
    RTF > 1.0  =>  slower than real time (can't keep up with a stream)

This script talks to the REST endpoint, not the WebSocket. REST path is
higher latency than streaming — use this for relative model comparison and
for quality spot-checks (you play the saved WAVs by ear).
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import httpx

try:
    import soundfile as sf
except ImportError:
    sf = None  # optional — only needed to compute duration from MP3

from rich.console import Console
from rich.table import Table

MODELS = ["qwen3-tts"]
console = Console()


@dataclass
class BenchResult:
    model: str
    phrase: str
    ttfa_ms: int = 0
    total_ms: int = 0
    audio_duration_s: float = 0.0
    rtf: float = 0.0
    bytes: int = 0
    error: str = ""


def run_one(
    client: httpx.Client,
    base_url: str,
    api_key: str,
    model: str,
    phrase: str,
    output_dir: Path,
    index: int,
) -> BenchResult:
    """Call /v1/audio/speech once, time the full roundtrip, save WAV."""
    result = BenchResult(model=model, phrase=phrase)

    t0 = time.perf_counter()
    try:
        r = client.post(
            f"{base_url}/v1/audio/speech",
            headers={"X-API-Key": api_key, "Content-Type": "application/json"},
            json={
                "model": model,
                "input": phrase,
                "voice": "default",
                "response_format": "wav",  # wav so we can measure duration reliably
                "speed": 1.0,
            },
            timeout=60.0,
        )
    except httpx.HTTPError as e:
        result.error = f"http_error: {e}"
        return result

    t1 = time.perf_counter()
    result.total_ms = int((t1 - t0) * 1000)
    # Server's own TTFA measurement is returned in the header — we prefer it
    # when available since it excludes network RTT.
    result.ttfa_ms = int(r.headers.get("x-ttfa-ms", "0") or "0") or result.total_ms

    if r.status_code != 200:
        result.error = f"http_{r.status_code}: {r.text[:160]}"
        return result

    audio_bytes = r.content
    result.bytes = len(audio_bytes)

    # Save for manual listening.
    safe_model = model.replace("/", "_")
    filename = f"{safe_model}__{index:02d}.wav"
    (output_dir / filename).write_bytes(audio_bytes)

    # Compute real duration from the saved file (only if soundfile is
    # available — the Docker image has it, a bare CLI run may not).
    if sf is not None:
        try:
            wave, sr = sf.read(io.BytesIO(audio_bytes))
            result.audio_duration_s = len(wave) / sr
            if result.audio_duration_s > 0:
                result.rtf = (result.total_ms / 1000.0) / result.audio_duration_s
        except Exception:
            pass

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark both TTS models.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--api-key", default="dev-local-key-change-me")
    parser.add_argument(
        "--phrases-file",
        default=str(Path(__file__).parent / "test_phrases.txt"),
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).parent / "output"),
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=MODELS,
        help="Which model names to test (default: both).",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    phrases: List[str] = [
        line.strip()
        for line in Path(args.phrases_file).read_text().splitlines()
        if line.strip()
    ]
    console.print(
        f"[bold]TTS benchmark[/bold] | {len(phrases)} phrases | models: {args.models}"
    )
    console.print(f"Server: {args.base_url}  |  Output: {output_dir}")

    results: List[BenchResult] = []
    with httpx.Client() as client:
        for model in args.models:
            console.print(f"\n[cyan]== {model} ==[/cyan]")
            for idx, phrase in enumerate(phrases, start=1):
                res = run_one(client, args.base_url, args.api_key, model, phrase, output_dir, idx)
                results.append(res)
                status = "[red]ERR[/red]" if res.error else "[green]OK[/green]"
                console.print(
                    f"  {idx:02d}. {status}  ttfa={res.ttfa_ms}ms  "
                    f"total={res.total_ms}ms  dur={res.audio_duration_s:.2f}s  "
                    f"rtf={res.rtf:.2f}  {res.error}"
                )

    # ---- Summary table ----
    table = Table(title="Benchmark summary", show_lines=True)
    table.add_column("Model", style="cyan")
    table.add_column("Runs", justify="right")
    table.add_column("Errors", justify="right", style="red")
    table.add_column("Mean TTFA (ms)", justify="right")
    table.add_column("Mean total (ms)", justify="right")
    table.add_column("Mean audio (s)", justify="right")
    table.add_column("Mean RTF", justify="right")

    for model in args.models:
        subset = [r for r in results if r.model == model]
        ok = [r for r in subset if not r.error]
        if not ok:
            table.add_row(model, str(len(subset)), str(len(subset) - len(ok)), "-", "-", "-", "-")
            continue
        n = len(ok)
        table.add_row(
            model,
            str(len(subset)),
            str(len(subset) - n),
            f"{sum(r.ttfa_ms for r in ok) / n:.0f}",
            f"{sum(r.total_ms for r in ok) / n:.0f}",
            f"{sum(r.audio_duration_s for r in ok) / n:.2f}",
            f"{sum(r.rtf for r in ok) / n:.2f}",
        )

    console.print()
    console.print(table)

    # Save raw results as JSONL for later analysis.
    jsonl_path = output_dir / "results.jsonl"
    with jsonl_path.open("w") as f:
        for r in results:
            f.write(json.dumps(r.__dict__) + "\n")
    console.print(f"\nRaw results: {jsonl_path}")

    return 0 if all(not r.error for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
