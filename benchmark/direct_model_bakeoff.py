"""Direct bakeoff for Qwen3-TTS and Chatterbox on a GPU box.

This bypasses the API scaffold and exercises the official model packages
directly. Use it when you want a first-pass quality/latency comparison before
adding a model to the FastAPI wrappers.

Example:

    python -m benchmark.direct_model_bakeoff \
        --phrases-file benchmark/test_phrases.txt \
        --output-dir benchmark/direct_output \
        --qwen-model-id Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice \
        --qwen-speaker Aiden \
        --qwen-language English \
        --qwen-instruct "Professional and friendly tone."

Primary-source references used for this script:
    * QwenLM/Qwen3-TTS README
    * resemble-ai/chatterbox README
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List

import numpy as np
import soundfile as sf
import torch
from rich.console import Console
from rich.table import Table

console = Console()


@dataclass
class BakeoffResult:
    model: str
    phrase: str
    total_ms: int = 0
    audio_duration_s: float = 0.0
    rtf: float = 0.0
    output_path: str = ""
    error: str = ""


def _load_phrases(path: Path) -> List[str]:
    return [line.strip() for line in path.read_text().splitlines() if line.strip()]


def _synchronize_cuda() -> None:
    if torch.cuda.is_available():
        torch.cuda.synchronize()


def _to_numpy_mono(audio) -> np.ndarray:
    """Normalize model output to a 1D float32 numpy array."""
    if isinstance(audio, torch.Tensor):
        arr = audio.detach().float().cpu().numpy()
    else:
        arr = np.asarray(audio, dtype=np.float32)

    arr = np.squeeze(arr)
    if arr.ndim == 0:
        return np.asarray([float(arr)], dtype=np.float32)
    if arr.ndim == 1:
        return arr.astype(np.float32, copy=False)

    # Chatterbox may return [channels, frames] or [batch, frames].
    return arr.reshape(-1, arr.shape[-1])[0].astype(np.float32, copy=False)


def _persist_audio(path: Path, waveform: np.ndarray, sample_rate: int) -> float:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, waveform, sample_rate)
    return len(waveform) / sample_rate if sample_rate > 0 else 0.0


def _measure_and_save(
    model_name: str,
    phrase: str,
    output_path: Path,
    generate_fn,
):
    _synchronize_cuda()
    t0 = time.perf_counter()
    audio, sample_rate = generate_fn()
    _synchronize_cuda()
    total_ms = int((time.perf_counter() - t0) * 1000)

    waveform = _to_numpy_mono(audio)
    duration_s = _persist_audio(output_path, waveform, sample_rate)
    rtf = (total_ms / 1000.0) / duration_s if duration_s > 0 else 0.0

    return BakeoffResult(
        model=model_name,
        phrase=phrase,
        total_ms=total_ms,
        audio_duration_s=duration_s,
        rtf=rtf,
        output_path=str(output_path),
    )


def run_qwen(args, phrases: Iterable[str], output_dir: Path) -> List[BakeoffResult]:
    from qwen_tts import Qwen3TTSModel

    dtype = {
        "bfloat16": torch.bfloat16,
        "float16": torch.float16,
    }[args.qwen_dtype]

    model = Qwen3TTSModel.from_pretrained(
        args.qwen_model_id,
        device_map="cuda:0",
        dtype=dtype,
        attn_implementation=args.qwen_attn_implementation,
    )

    results: List[BakeoffResult] = []
    for idx, phrase in enumerate(phrases, start=1):
        output_path = output_dir / "qwen3-tts" / f"qwen3-tts__{idx:02d}.wav"
        try:
            result = _measure_and_save(
                model_name="qwen3-tts",
                phrase=phrase,
                output_path=output_path,
                generate_fn=lambda: model.generate_custom_voice(
                    text=phrase,
                    language=args.qwen_language,
                    speaker=args.qwen_speaker,
                    instruct=args.qwen_instruct or None,
                ),
            )
        except Exception as exc:  # pragma: no cover - remote-only path
            result = BakeoffResult(
                model="qwen3-tts",
                phrase=phrase,
                output_path=str(output_path),
                error=str(exc),
            )
        results.append(result)
    return results


def run_chatterbox(args, phrases: Iterable[str], output_dir: Path) -> List[BakeoffResult]:
    if args.chatterbox_mode == "english":
        from chatterbox.tts import ChatterboxTTS

        model_name = "chatterbox"
        model = ChatterboxTTS.from_pretrained(device="cuda")

        def generate(phrase: str):
            wav = model.generate(
                phrase,
                audio_prompt_path=args.chatterbox_audio_prompt or None,
            )
            return wav, model.sr

    elif args.chatterbox_mode == "multilingual":
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS

        model_name = "chatterbox-multilingual"
        model = ChatterboxMultilingualTTS.from_pretrained(device="cuda")

        def generate(phrase: str):
            wav = model.generate(
                phrase,
                language_id=args.chatterbox_language_id,
                audio_prompt_path=args.chatterbox_audio_prompt or None,
            )
            return wav, model.sr

    else:
        from chatterbox.tts_turbo import ChatterboxTurboTTS

        model_name = "chatterbox-turbo"
        model = ChatterboxTurboTTS.from_pretrained(device="cuda")

        if not args.chatterbox_audio_prompt:
            raise ValueError("--chatterbox-audio-prompt is required for turbo mode")

        def generate(phrase: str):
            wav = model.generate(
                phrase,
                audio_prompt_path=args.chatterbox_audio_prompt,
            )
            return wav, model.sr

    results: List[BakeoffResult] = []
    for idx, phrase in enumerate(phrases, start=1):
        output_path = output_dir / model_name / f"{model_name}__{idx:02d}.wav"
        try:
            result = _measure_and_save(
                model_name=model_name,
                phrase=phrase,
                output_path=output_path,
                generate_fn=lambda phrase=phrase: generate(phrase),
            )
        except Exception as exc:  # pragma: no cover - remote-only path
            result = BakeoffResult(
                model=model_name,
                phrase=phrase,
                output_path=str(output_path),
                error=str(exc),
            )
        results.append(result)
    return results


def _print_summary(results: List[BakeoffResult]) -> None:
    table = Table(title="Direct model bakeoff", show_lines=True)
    table.add_column("Model", style="cyan")
    table.add_column("Runs", justify="right")
    table.add_column("Errors", justify="right", style="red")
    table.add_column("Mean total (ms)", justify="right")
    table.add_column("Mean audio (s)", justify="right")
    table.add_column("Mean RTF", justify="right")

    models = sorted({row.model for row in results})
    for model_name in models:
        subset = [row for row in results if row.model == model_name]
        ok = [row for row in subset if not row.error]
        if not ok:
            table.add_row(model_name, str(len(subset)), str(len(subset)), "-", "-", "-")
            continue

        n = len(ok)
        table.add_row(
            model_name,
            str(len(subset)),
            str(len(subset) - n),
            f"{sum(row.total_ms for row in ok) / n:.0f}",
            f"{sum(row.audio_duration_s for row in ok) / n:.2f}",
            f"{sum(row.rtf for row in ok) / n:.2f}",
        )

    console.print()
    console.print(table)


def main() -> int:
    parser = argparse.ArgumentParser(description="Direct Qwen3-TTS vs Chatterbox bakeoff.")
    parser.add_argument(
        "--phrases-file",
        default=str(Path(__file__).with_name("test_phrases.txt")),
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).with_name("direct_output")),
    )
    parser.add_argument(
        "--skip-qwen",
        action="store_true",
        help="Skip Qwen3-TTS generation.",
    )
    parser.add_argument(
        "--skip-chatterbox",
        action="store_true",
        help="Skip Chatterbox generation.",
    )

    parser.add_argument(
        "--qwen-model-id",
        default="Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
    )
    parser.add_argument("--qwen-speaker", default="Aiden")
    parser.add_argument("--qwen-language", default="English")
    parser.add_argument("--qwen-instruct", default="Professional and friendly tone.")
    parser.add_argument(
        "--qwen-dtype",
        choices=["bfloat16", "float16"],
        default="bfloat16",
    )
    parser.add_argument(
        "--qwen-attn-implementation",
        default="flash_attention_2",
    )

    parser.add_argument(
        "--chatterbox-mode",
        choices=["english", "multilingual", "turbo"],
        default="english",
    )
    parser.add_argument(
        "--chatterbox-language-id",
        default="en",
        help="Only used for multilingual mode.",
    )
    parser.add_argument(
        "--chatterbox-audio-prompt",
        default="",
        help="Optional reference WAV path. Required for turbo mode.",
    )

    args = parser.parse_args()

    phrases = _load_phrases(Path(args.phrases_file))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    console.print(
        f"[bold]Direct bakeoff[/bold] | {len(phrases)} phrases | output={output_dir}"
    )

    results: List[BakeoffResult] = []
    if not args.skip_qwen:
        console.print("\n[cyan]== qwen3-tts ==[/cyan]")
        results.extend(run_qwen(args, phrases, output_dir))
    if not args.skip_chatterbox:
        console.print(f"\n[cyan]== {args.chatterbox_mode} ==[/cyan]")
        results.extend(run_chatterbox(args, phrases, output_dir))

    for idx, row in enumerate(results, start=1):
        status = "[red]ERR[/red]" if row.error else "[green]OK[/green]"
        console.print(
            f"{idx:02d}. {status}  model={row.model}  total={row.total_ms}ms  "
            f"dur={row.audio_duration_s:.2f}s  rtf={row.rtf:.2f}  {row.error}"
        )

    _print_summary(results)

    jsonl_path = output_dir / "results.jsonl"
    with jsonl_path.open("w") as handle:
        for row in results:
            handle.write(json.dumps(asdict(row)) + "\n")
    console.print(f"\nRaw results: {jsonl_path}")

    return 0 if all(not row.error for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
