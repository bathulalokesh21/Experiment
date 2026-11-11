"""Neural voices (edge-tts), streamed. First bytes are awaited, a failed line is
retried once, then a persona-matched fallback voice is used: FRIDAY never turns
into a random male voice mid-sentence. Optional own-voice slots: recorded clips
and Piper models under data/voices/<persona>/."""
from __future__ import annotations

import hashlib
import io
import math
import re
import struct
import wave

from . import config

VOICES = {
    "jarvis": {"voice": "en-GB-RyanNeural", "fallback": "en-GB-ThomasNeural", "rate": "+4%", "pitch": "-2Hz"},
    "friday": {"voice": "en-IE-EmilyNeural", "fallback": "en-GB-SoniaNeural", "rate": "+8%", "pitch": "+0Hz"},
    "robin": {"voice": "en-US-AvaMultilingualNeural", "fallback": "en-US-EmmaMultilingualNeural", "rate": "-4%",
              "pitch": "-1Hz"},
}
_synth_override = None  # tests: async generator factory (text, voice, rate, pitch)


class VoiceError(Exception):
    pass


def set_synth(fn) -> None:
    global _synth_override
    _synth_override = fn


def settings_for(persona: str) -> dict:
    base = dict(VOICES.get(persona, VOICES["jarvis"]))
    key = persona.upper()
    base["voice"] = config.env(f"{key}_VOICE", base["voice"])
    base["fallback"] = config.env(f"{key}_FALLBACK_VOICE", base["fallback"])
    base["rate"] = config.env(f"{key}_RATE", base["rate"])
    base["pitch"] = config.env(f"{key}_PITCH", base["pitch"])
    return base


def clean_for_speech(text: str) -> str:
    """What the voice should actually say: no markdown, no URLs, no long comma pauses."""
    text = re.sub(r"```.*?```", " code block omitted. ", text, flags=re.S)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"https?://\S+", "a link", text)
    text = re.sub(r"^\s*[-*•]\s+", "", text, flags=re.M)
    text = re.sub(r"^\s*#+\s*", "", text, flags=re.M)
    text = re.sub(r"[*_~>|]", "", text)
    text = text.replace("₹", " rupees ").replace("°C", " degrees").replace("&", " and ")
    text = re.sub(r"\s*[—–]\s*", ", ", text)
    if config.env("VOICE_KEEP_COMMAS", "") != "1":
        # neural voices pause on every comma; drop the ones that only slow a short phrase down
        text = re.sub(r"(?<=[A-Za-z]),\s+(?=(sir|boss|love|Love|Nikesh)\b)", " ", text)
        text = re.sub(r"\b(Well|So|Now|Right|Oh|Ah|Yes|No|Okay|OK|Sure|Indeed|Actually),\s+", r"\1 ", text)
    return re.sub(r"\s+", " ", text).strip()


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:60]


def own_clip(persona: str, text: str) -> bytes | None:
    """data/voices/<persona>/clips/<slug>.mp3|wav: his own recordings for exact phrases."""
    base = config.data("voices", persona, "clips")
    for ext in (".mp3", ".wav"):
        path = base / (_slug(text) + ext)
        if path.exists():
            return path.read_bytes()
    return None


def piper_model(persona: str):
    folder = config.data("voices", persona)
    models = sorted(folder.glob("*.onnx")) if folder.exists() else []
    return models[0] if models else None


def _piper(persona: str, text: str) -> bytes | None:
    model = piper_model(persona)
    if model is None:
        return None
    try:
        from piper import PiperVoice  # optional dependency
        voice = PiperVoice.load(str(model))
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            voice.synthesize(text, wav)
        return buf.getvalue()
    except Exception:
        return None


async def _edge(text: str, voice: str, rate: str, pitch: str):
    if _synth_override is not None:
        async for chunk in _synth_override(text, voice, rate, pitch):
            yield chunk
        return
    import edge_tts
    comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    async for item in comm.stream():
        if item.get("type") == "audio" and item.get("data"):
            yield item["data"]


def _cache_path(persona: str, text: str, cfg: dict):
    key = hashlib.sha1(f"{persona}|{cfg['voice']}|{cfg['rate']}|{cfg['pitch']}|{text}".encode()).hexdigest()
    return config.data("cache", "tts", key + ".mp3")


async def synth(persona: str, text: str, cache: bool = False):
    """Async generator of audio bytes. Raises VoiceError before yielding anything if no
    voice works, so the caller never sends empty audio."""
    spoken = clean_for_speech(text)
    if not spoken or not re.search(r"[A-Za-z0-9]", spoken):
        raise VoiceError("nothing to say")
    clip = own_clip(persona, spoken)
    if clip:
        yield clip
        return
    piper_audio = _piper(persona, spoken)
    if piper_audio:
        yield piper_audio
        return
    cfg = settings_for(persona)
    cached = _cache_path(persona, spoken, cfg)
    if cache and cached.exists() and cached.stat().st_size > 200:
        yield cached.read_bytes()
        return
    attempts = [(cfg["voice"], cfg["rate"], cfg["pitch"]), (cfg["voice"], cfg["rate"], cfg["pitch"]),
                (cfg["fallback"], cfg["rate"], "+0Hz")]
    last_error = None
    for voice, rate, pitch in attempts:
        try:
            stream = _edge(spoken, voice, rate, pitch)
            first = await anext(stream, None)  # await the first bytes before committing
            if not first:
                raise VoiceError("the voice service returned no audio")
            collected = [first]
            yield first
            async for chunk in stream:
                collected.append(chunk)
                yield chunk
            if cache:
                cached.parent.mkdir(parents=True, exist_ok=True)
                cached.write_bytes(b"".join(collected))
            return
        except VoiceError as exc:
            last_error = exc
        except Exception as exc:
            last_error = exc
    raise VoiceError(f"voice unavailable ({type(last_error).__name__ if last_error else 'unknown'})")


def tone_wav(seconds: float = 0.35, freq: float = 220.0) -> bytes:
    """A soft tone as WAV: the fake voice used by tests and JARVIS_FAKE=1 demos."""
    rate = 16000
    n = int(rate * seconds)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        frames = bytearray()
        for i in range(n):
            env = min(1.0, i / 400, (n - i) / 400)
            wob = 0.6 + 0.4 * math.sin(2 * math.pi * 6 * i / rate)
            frames += struct.pack("<h", int(9000 * env * wob * math.sin(2 * math.pi * freq * i / rate)))
        wav.writeframes(bytes(frames))
    return buf.getvalue()


async def fake_synth(text, voice, rate, pitch):
    words = max(1, len(text.split()))
    freq = 150.0 if "Ryan" in voice or "Thomas" in voice else 240.0
    yield tone_wav(min(4.0, 0.18 * words + 0.2), freq)
