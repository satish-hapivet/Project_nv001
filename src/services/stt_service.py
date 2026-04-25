"""
NIMS Hospital Voice Assistant – STT Service (faster-whisper)
-------------------------------------------------------------
Production-grade Speech-to-Text with:
  - Pre-emphasis high-pass filter (suppresses low-frequency room noise)
  - Amplitude normalisation (consistent input level)
  - VAD filter + no-speech guard
  - Per-turn language auto-detection (en/hi/te)
  - Two-pass Indic transcription (detect → re-transcribe with hint)
  - Confidence gating via avg_logprob
  - Unsupported-script rejection

Ported from the proven voice_agent local_services.LocalWhisperSTT.
"""
import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Optional

import numpy as np
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)


# ── STT Result ────────────────────────────────────────────────────────────

@dataclass
class STTResult:
    """Structured result from speech-to-text transcription."""
    text: str
    language: str
    lang_probability: float
    avg_logprob: float          # higher = more confident
    no_speech_prob: float       # probability audio was NOT speech
    is_confident: bool          # meets minimum confidence threshold

    @property
    def summary(self) -> str:
        return (
            f"lang={self.language}(p={self.lang_probability:.2f}) "
            f"logprob={self.avg_logprob:.2f} "
            f"no_speech={self.no_speech_prob:.2f} "
            f"confident={self.is_confident}"
        )


# ── STT Service ────────────────────────────────────────────────────────────

class STTService:
    """
    Production-grade Whisper STT service for the NIMS Hospital pipeline.

    Model selection (configurable via WHISPER_MODEL env var):
        'medium' (769M, default) – best Indic accuracy on CPU
        'small'  (244M) – faster but weaker on Telugu/Hindi
        'large-v3' (1.5B) – highest accuracy, slow on CPU
    """

    # Transcription parameters
    NO_SPEECH_THRESHOLD = 0.50
    BEAM_SIZE           = 5

    # Language detection
    SUPPORTED_LANGS = {"en", "hi", "te"}
    INDIC_LANGS     = {"hi", "te"}
    MIN_LANG_PROB   = 0.55

    # Confidence gating
    MIN_AVG_LOGPROB = -0.85

    # Script ranges for mismatch detection
    SCRIPT_RANGES = {
        "te": (0x0C00, 0x0C7F),
        "hi": (0x0900, 0x097F),
    }

    # Unsupported scripts (Bengali, Tamil, Kannada, Malayalam, etc.)
    UNSUPPORTED_SCRIPT_RANGES = [
        (0x0980, 0x09FF),  # Bengali
        (0x0B80, 0x0BFF),  # Tamil
        (0x0C80, 0x0CFF),  # Kannada
        (0x0D00, 0x0D7F),  # Malayalam
        (0x0A00, 0x0A7F),  # Gurmukhi
        (0x0B00, 0x0B7F),  # Odia
    ]

    DEFAULT_MODEL = "medium"

    def __init__(self):
        self.model: Optional[WhisperModel] = None
        self._model_size: str = ""
        self._initialized = False

    async def initialize(self, model_size: str = None, device: str = "cpu") -> bool:
        """Load the Whisper model. Runs in executor to avoid blocking."""
        model_size = model_size or os.getenv("WHISPER_MODEL", self.DEFAULT_MODEL)
        try:
            loop = asyncio.get_running_loop()
            self.model = await loop.run_in_executor(
                None,
                lambda: WhisperModel(model_size, device=device, compute_type="int8"),
            )
            self._model_size = model_size
            self._initialized = True
            logger.info("STT service initialized: model=%s, device=%s, int8", model_size, device)
            return True
        except Exception as e:
            logger.error("STT initialization failed: %s", e)
            return False

    # ── Pre-processing ────────────────────────────────────────────────

    @staticmethod
    def _pre_emphasis(audio: np.ndarray, coeff: float = 0.97) -> np.ndarray:
        """High-pass filter: lifts consonants, suppresses low rumble."""
        return np.append(audio[0], audio[1:] - coeff * audio[:-1])

    @staticmethod
    def _normalize(audio: np.ndarray) -> np.ndarray:
        """Peak-normalize to ±0.9 for consistent Whisper input levels."""
        peak = np.max(np.abs(audio))
        if peak < 1e-6:
            return audio
        return audio * (0.9 / peak)

    def _preprocess(self, audio_bytes: bytes) -> np.ndarray:
        """Raw PCM int16 bytes → pre-emphasized, normalized float32 array."""
        audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
        audio_float32 = audio_int16.astype(np.float32) / 32768.0
        audio_float32 = self._pre_emphasis(audio_float32)
        audio_float32 = self._normalize(audio_float32)
        return audio_float32

    # ── Transcription internals ───────────────────────────────────────

    @staticmethod
    def _collect_segments(segs):
        """Consume segment generator and compute aggregate metrics."""
        segments = list(segs)
        text = "".join(s.text for s in segments).strip()
        if segments:
            total_tokens = sum(max(len(s.tokens), 1) for s in segments)
            avg_logprob = sum(
                s.avg_logprob * max(len(s.tokens), 1) for s in segments
            ) / total_tokens
            no_speech_prob = max(s.no_speech_prob for s in segments)
        else:
            avg_logprob = -float("inf")
            no_speech_prob = 1.0
        return text, avg_logprob, no_speech_prob

    def _transcribe_once(self, audio: np.ndarray, language=None):
        """Run a single transcription pass."""
        segs, info = self.model.transcribe(
            audio,
            language=language,
            beam_size=self.BEAM_SIZE,
            vad_filter=True,
            vad_parameters={
                "min_silence_duration_ms": 250,
                "speech_pad_ms": 100,
            },
            no_speech_threshold=self.NO_SPEECH_THRESHOLD,
            condition_on_previous_text=False,
            temperature=0.0,
        )
        text, avg_logprob, no_speech_prob = self._collect_segments(segs)
        detected_lang = info.language or "en"
        lang_prob = getattr(info, "language_probability", 0.0)
        return text, detected_lang, lang_prob, avg_logprob, no_speech_prob

    def _run_transcribe(self, audio: np.ndarray, language: str = None):
        """
        Synchronous transcription with two-pass Indic strategy.

        Pass 1 (auto-detect): language=None → get detected language
        Pass 2 (hinted): language=<detected> → force correct script

        Fixes Whisper outputting Devanagari for Telugu.
        """
        if language is not None:
            return self._transcribe_once(audio, language=language)

        text, detected_lang, lang_prob, avg_logprob, no_speech_prob = (
            self._transcribe_once(audio, language=None)
        )

        # Re-transcribe with hint for Indic languages
        if (
            detected_lang in self.INDIC_LANGS
            and lang_prob >= self.MIN_LANG_PROB
            and text.strip()
        ):
            logger.info(
                "[STT] Two-pass: detected %s (p=%.2f), re-transcribing with hint",
                detected_lang, lang_prob,
            )
            text2, _, _, avg_logprob2, no_speech_prob2 = (
                self._transcribe_once(audio, language=detected_lang)
            )
            if text2.strip():
                return text2, detected_lang, lang_prob, avg_logprob2, no_speech_prob2

        return text, detected_lang, lang_prob, avg_logprob, no_speech_prob

    # ── Public async API ──────────────────────────────────────────────

    async def transcribe(self, audio_bytes: bytes, language_hint: str = None) -> STTResult:
        """
        Transcribe raw audio bytes → STTResult.

        Args:
            audio_bytes:   Raw PCM int16 audio at 16 kHz mono.
            language_hint: Optional ISO 639-1 code ('en', 'hi', 'te').
                           Forces Whisper decoder vocabulary for that language.
        """
        if not self._initialized:
            return STTResult(
                text="", language="en", lang_probability=0.0,
                avg_logprob=-float("inf"), no_speech_prob=1.0, is_confident=False,
            )

        try:
            audio = self._preprocess(audio_bytes)
            loop = asyncio.get_running_loop()

            text, detected_lang, lang_prob, avg_logprob, no_speech_prob = (
                await loop.run_in_executor(
                    None, self._run_transcribe, audio, language_hint,
                )
            )

            # Per-turn language decision
            if language_hint and language_hint in self.SUPPORTED_LANGS:
                lang = language_hint
            elif lang_prob >= self.MIN_LANG_PROB and detected_lang in self.SUPPORTED_LANGS:
                lang = detected_lang
            else:
                lang = "en"
                if text.strip():
                    logger.info(
                        "Language detection: %s (prob=%.2f) → using 'en' this turn",
                        detected_lang, lang_prob,
                    )

            # Confidence assessment
            is_confident = (
                bool(text.strip())
                and avg_logprob >= self.MIN_AVG_LOGPROB
                and no_speech_prob < 0.7
            )

            # Reject unsupported scripts (Tamil, Bengali, etc.)
            if is_confident and text.strip():
                non_ascii = [c for c in text if ord(c) > 0x007F]
                if non_ascii:
                    unsupported_count = sum(
                        1 for c in non_ascii
                        for lo, hi in self.UNSUPPORTED_SCRIPT_RANGES
                        if lo <= ord(c) <= hi
                    )
                    if unsupported_count > len(non_ascii) * 0.3:
                        logger.warning(
                            "[STT] Unsupported script detected (%.0f%% chars) — low-confidence",
                            unsupported_count / len(non_ascii) * 100,
                        )
                        is_confident = False

            # Script-mismatch detection (e.g. Devanagari output for Telugu)
            if is_confident and lang in self.SCRIPT_RANGES and text.strip():
                expected_lo, expected_hi = self.SCRIPT_RANGES[lang]
                script_chars = [c for c in text if ord(c) > 0x007F]
                if script_chars:
                    in_script = sum(
                        1 for c in script_chars
                        if expected_lo <= ord(c) <= expected_hi
                    )
                    ratio = in_script / len(script_chars)
                    if ratio < 0.5:
                        logger.warning(
                            "[STT] Script mismatch: lang=%s but only %.0f%% "
                            "in expected range — low-confidence",
                            lang, ratio * 100,
                        )
                        is_confident = False

            result = STTResult(
                text=text,
                language=lang,
                lang_probability=lang_prob,
                avg_logprob=avg_logprob,
                no_speech_prob=no_speech_prob,
                is_confident=is_confident,
            )
            logger.info("[STT] '%s' | %s", text[:80] if text else "(empty)", result.summary)
            return result

        except Exception as e:
            logger.error("STT Error: %s", e)
            return STTResult(
                text="", language="en", lang_probability=0.0,
                avg_logprob=-float("inf"), no_speech_prob=1.0, is_confident=False,
            )

    async def health_check(self) -> dict:
        return {
            "initialized": self._initialized,
            "model_size": self._model_size,
        }


# ── Global singleton ─────────────────────────────────────────────────────

_stt_service: Optional[STTService] = None


async def get_stt_service(model_size: str = None, device: str = "cpu") -> STTService:
    global _stt_service
    if _stt_service is None:
        _stt_service = STTService()
        await _stt_service.initialize(model_size=model_size, device=device)
    return _stt_service
