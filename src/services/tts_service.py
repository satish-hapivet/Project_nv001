"""
NIMS Hospital Voice Assistant – TTS Service (edge-tts)
-------------------------------------------------------
Microsoft Edge neural TTS with per-language Indian voice mapping.
Async, high-quality, replaces gTTS for production use.

Ported from the proven voice_agent local_services.LocalEdgeTTS.
"""
import asyncio
import logging
import os
import tempfile
from datetime import datetime
from typing import Optional

import edge_tts

logger = logging.getLogger(__name__)


class TTSService:
    """
    Edge-TTS service for the NIMS Hospital pipeline.

    Features:
      - Indian English, Hindi, Telugu neural voices
      - Async generation (non-blocking)
      - Returns bytes (for WebSocket streaming) or saves to file (for REST)
    """

    VOICE_MAP = {
        "en": "en-IN-NeerjaNeural",   # Indian English
        "hi": "hi-IN-NeerjaNeural",   # Hindi
        "te": "te-IN-ShrutiNeural",   # Telugu
    }
    DEFAULT_VOICE = "en-IN-NeerjaNeural"

    def __init__(self):
        self._audio_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "logs", "audio",
        )
        os.makedirs(self._audio_dir, exist_ok=True)
        self._initialized = True
        logger.info("TTS service initialized (edge-tts)")

    async def generate_bytes(self, text: str, lang: str = "en") -> Optional[bytes]:
        """
        Generate TTS audio and return raw MP3 bytes.
        Used by WebSocket endpoint to stream audio directly.
        """
        if not text:
            return None

        voice = self.VOICE_MAP.get(lang, self.DEFAULT_VOICE)
        fd, tmp_path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)

        try:
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(tmp_path)
            with open(tmp_path, "rb") as f:
                data = f.read()
            return data
        except OSError as e:
            logger.warning("TTS unavailable (network): %s", type(e).__name__)
            return None
        except Exception as e:
            logger.warning("TTS error: %s", str(e).split("\n")[0][:120])
            return None
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    async def generate_file(self, text: str, lang: str = "en") -> Optional[str]:
        """
        Generate TTS audio and save to logs/audio/ directory.
        Returns the file path. Used by REST endpoint.
        """
        if not text:
            return None

        voice = self.VOICE_MAP.get(lang, self.DEFAULT_VOICE)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        filename = f"response_{timestamp}_{lang}.mp3"
        filepath = os.path.join(self._audio_dir, filename)

        try:
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(filepath)
            logger.info("[TTS] lang=%s voice=%s file=%s", lang, voice, filename)
            return filepath
        except OSError as e:
            logger.warning("TTS unavailable (network): %s", type(e).__name__)
            return None
        except Exception as e:
            logger.warning("TTS error: %s", str(e).split("\n")[0][:120])
            return None

    async def health_check(self) -> dict:
        return {
            "initialized": self._initialized,
            "voices": list(self.VOICE_MAP.keys()),
        }


# ── Global singleton ─────────────────────────────────────────────────────

_tts_service: Optional[TTSService] = None


async def get_tts_service() -> TTSService:
    global _tts_service
    if _tts_service is None:
        _tts_service = TTSService()
    return _tts_service
