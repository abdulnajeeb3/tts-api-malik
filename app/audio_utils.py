"""Audio encoding helpers.

Responsibilities:
  * Convert float32 waveforms in [-1, 1] to PCM16 bytes for streaming.
  * Encode a full waveform to mp3/wav/opus/flac for the REST endpoint.
  * Chunk a waveform into fixed-duration pieces (fallback path for models
    that don't stream natively).
  * Normalize package-specific outputs into a mono float32 waveform.
  * Resample a waveform when the request sample rate differs from the
    model-native sample rate.

Keep this module numpy-only on the hot path — no torch — to stay light for
the streaming thread.
"""
from __future__ import annotations

import io
from typing import Any, Iterator, Literal

import numpy as np
import soundfile as sf


RestFormat = Literal["mp3", "wav", "opus", "flac"]


def to_mono_float32(audio: Any) -> np.ndarray:
    """Normalize model output to a 1D float32 numpy array.

    Handles plain numpy arrays, Python sequences, and torch tensors without
    importing torch into this module.
    """
    if isinstance(audio, (list, tuple)):
        if not audio:
            return np.asarray([], dtype=np.float32)
        audio = audio[0]

    if hasattr(audio, "detach") and hasattr(audio, "cpu"):
        arr = audio.detach().float().cpu().numpy()
    else:
        arr = np.asarray(audio, dtype=np.float32)

    arr = np.squeeze(arr)
    if arr.ndim == 0:
        return np.asarray([float(arr)], dtype=np.float32)
    if arr.ndim == 1:
        return arr.astype(np.float32, copy=False)

    return arr.reshape(-1, arr.shape[-1])[0].astype(np.float32, copy=False)


def resample_waveform(
    waveform: np.ndarray,
    src_rate: int,
    dst_rate: int,
) -> np.ndarray:
    """Resample a mono float32 waveform with linear interpolation."""
    if src_rate <= 0 or dst_rate <= 0:
        raise ValueError(f"sample rates must be positive, got {src_rate} -> {dst_rate}")
    if src_rate == dst_rate or len(waveform) == 0:
        return waveform.astype(np.float32, copy=False)

    duration_s = len(waveform) / float(src_rate)
    dst_len = max(1, int(round(duration_s * dst_rate)))
    src_positions = np.linspace(0.0, len(waveform) - 1, num=len(waveform), dtype=np.float32)
    dst_positions = np.linspace(0.0, len(waveform) - 1, num=dst_len, dtype=np.float32)
    return np.interp(dst_positions, src_positions, waveform).astype(np.float32, copy=False)


# ---------- PCM conversion ----------

def float_to_pcm16(waveform: np.ndarray) -> bytes:
    """Convert float32/float64 in [-1, 1] to little-endian int16 PCM bytes."""
    if waveform.dtype != np.float32:
        waveform = waveform.astype(np.float32, copy=False)
    # Clip to avoid int16 wraparound on out-of-range values.
    np.clip(waveform, -1.0, 1.0, out=waveform)
    pcm = (waveform * 32767.0).astype(np.int16)
    return pcm.tobytes()


def pcm16_to_float(pcm_bytes: bytes) -> np.ndarray:
    pcm = np.frombuffer(pcm_bytes, dtype=np.int16)
    return pcm.astype(np.float32) / 32767.0


# ---------- Chunking (for models that produce full waveforms) ----------

def chunk_waveform(
    waveform: np.ndarray,
    sample_rate: int,
    chunk_ms: int = 200,
) -> Iterator[np.ndarray]:
    """Yield consecutive fixed-duration slices of `waveform`.

    Used as a fallback when a model returns the full audio at once: we still
    want to stream it to the client in WebSocket frames instead of one giant
    message, so chunk it and yield.
    """
    if waveform.ndim != 1:
        raise ValueError(f"expected mono waveform, got shape {waveform.shape}")
    samples_per_chunk = max(1, int(sample_rate * chunk_ms / 1000))
    for start in range(0, len(waveform), samples_per_chunk):
        yield waveform[start:start + samples_per_chunk]


# ---------- Full-waveform encoding (REST response path) ----------

def encode_waveform(
    waveform: np.ndarray,
    sample_rate: int,
    fmt: RestFormat,
) -> bytes:
    """Encode a full mono waveform to bytes of the requested container format.

    wav / flac: done in-process via soundfile.
    mp3 / opus: soundfile supports these via libsndfile >= 1.1 on the runtime
      image. If the local soundfile build doesn't support mp3, pydub+ffmpeg
      is used as a fallback (the Dockerfile installs ffmpeg).
    """
    if waveform.ndim != 1:
        raise ValueError(f"expected mono waveform, got shape {waveform.shape}")

    if fmt in ("wav", "flac"):
        buf = io.BytesIO()
        subtype = "PCM_16" if fmt == "wav" else None
        sf.write(buf, waveform, sample_rate, format=fmt.upper(), subtype=subtype)
        return buf.getvalue()

    if fmt == "opus":
        try:
            buf = io.BytesIO()
            sf.write(buf, waveform, sample_rate, format="OGG", subtype="OPUS")
            return buf.getvalue()
        except Exception:
            pass  # fall through to pydub/ffmpeg path below.

    if fmt == "mp3":
        try:
            buf = io.BytesIO()
            sf.write(buf, waveform, sample_rate, format="MP3")
            return buf.getvalue()
        except Exception:
            pass  # fall through to pydub/ffmpeg path below.

    # pydub fallback for formats soundfile can't handle on this system.
    # Uses ffmpeg under the hood (installed in the Docker image).
    from pydub import AudioSegment  # local import: optional hot-path dep.

    pcm_bytes = float_to_pcm16(waveform)
    segment = AudioSegment(
        data=pcm_bytes,
        sample_width=2,  # int16 = 2 bytes
        frame_rate=sample_rate,
        channels=1,
    )
    buf = io.BytesIO()
    segment.export(buf, format="mp3" if fmt == "mp3" else fmt)
    return buf.getvalue()


def content_type_for(fmt: RestFormat) -> str:
    return {
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "opus": "audio/ogg",
        "flac": "audio/flac",
    }[fmt]
