"""
OpenAI GPT-4o-mini Service for NIMS Hospital Voice Assistant
-------------------------------------------------------------
Provides:
  - NLU intent classification (12 intents, JSON-mode)
  - Contextual response generation
  - Language detection
  - TTS via gTTS fallback

Ported from the proven voice_agent NLU pipeline.
"""
import json
import logging
import os
import sys
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime

try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    AsyncOpenAI = None

try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import get_config

logger = logging.getLogger(__name__)


# ── Prompts (ported from voice_agent) ────────────────────────────────────

NLU_PROMPT = """
You are an intent classifier for a hospital voice assistant.
Analyse the user message and return ONLY a JSON object -- no prose, no markdown.

JSON schema:
{{
  "intent": "<one of: find_doctor | find_department | find_ward | find_nurse | check_appointment | book_appointment | hospital_info | emergency | pharmacy | facilities | greeting | unknown>",
  "confidence": <float 0.0-1.0>,
  "entities": {{
    "doctor_name":   "<partial name or null>",
    "dept_name":     "<department or specialization keyword or null>",
    "patient_name":  "<patient name or null>",
    "patient_phone": "<phone number or null>",
    "date":          "<ISO date YYYY-MM-DD or null>",
    "time":          "<appointment time like '10:00 AM' or null>",
    "ward_type":     "<ICU, General, Emergency or null>"
  }}
}}

Rules:
- confidence >= 0.75 means intent is clear enough to act on
- confidence < 0.75 means set intent to "unknown"
- Extract only what is explicitly mentioned.  Use null otherwise.
- If the user asks for "doctors in <department>" or "list doctors in <department>" or similar, use intent "find_doctor" with dept_name set to the department. Only use "find_department" when the user is asking about the department itself (location, phone, description), NOT about the doctors.
- Treat "Dr", "doctor", "डॉक्टर", "డాక్టర్" as doctor_name signals.
- Treat "pharmacy", "फार्मेसी", "ఫార్మసీ", "medicine", "दवाई" as pharmacy intent.
- Treat "OPD", "ICU", "bed", "ward", "बेड", "वार्ड", "పడక", "వార్డు" as find_ward signals.
- Treat "nurse", "नर्स", "నర్సు", "sister" as find_nurse signals.
- Treat "appointment", "book", "schedule", "अपॉइंटमेंट", "बुक", "అపాయింట్‌మెంట్", "బుక్" as appointment signals.
  If intent is to create/book a NEW appointment, use "book_appointment".
  If intent is to check/enquire about an EXISTING appointment, use "check_appointment".
- Treat "department", "विभाग", "విభాగం" as dept_name signals.
- Treat "parking", "ATM", "cafeteria", "lab", "blood bank", "facilities" as facilities intent.
- Treat "visiting hours", "visit time", "when can I visit", "visitor", "icu visiting" as hospital_info intent.

User message: "{user_text}"
"""

SYSTEM_PROMPT = """You are NIMS Assistant, a professional voice assistant for NIMS Multi-Speciality
Hospital, Punjagutta, Hyderabad.

LANGUAGE RULES (STRICT - MUST FOLLOW):
- You MUST respond ONLY in {response_language}. This is non-negotiable.
- Never switch language mid-response.
- If the response language is Hindi, use ONLY Devanagari script.
- If the response language is Telugu, use ONLY Telugu script.
- If the response language is English, use ONLY English.

RESPONSE RULES:
1. Maximum 2-3 short sentences. No bullet points. No markdown.
2. Base your answer ONLY on the DATABASE CONTEXT below.
   If the context says "(none)" or is empty, say you could not find
   that information and offer to help with something else.
   NEVER invent doctor names, room numbers, phone numbers, or any data
   not present in the context.
3. Never give medical advice or diagnose.
4. For emergencies always say: go to the Emergency Ward immediately.
5. Be warm, professional, and speak as if you are standing at the
   hospital reception desk.
6. When listing doctors, include their name, specialization, and
   availability. When listing wards, mention bed availability.

DATABASE CONTEXT (live data from PostgreSQL):
{context}
"""

FALLBACK = {
    "en": (
        "I'm sorry, I didn't quite catch that. "
        "Could you please ask about a doctor, department, ward, or your appointment?"
    ),
    "hi": (
        "माफ करें, मैं आपकी बात स्पष्ट नहीं समझ पाया। "
        "क्या आप किसी डॉक्टर, विभाग, वार्ड या अपॉइंटमेंट के बारे में पूछ सकते हैं?"
    ),
    "te": (
        "క్షమించండి, మీరు చెప్పింది సరిగా అర్థం కాలేదు. "
        "దయచేసి ఒక డాక్టర్, విభాగం, వార్డు లేదా అపాయింట్‌మెంట్ గురించి అడగగలరా?"
    ),
}

NLU_CONFIDENCE_THRESHOLD = 0.72  # canonical threshold (used by orchestrator)
MAX_NLU_RETRIES = 3


class OpenAIService:
    """
    OpenAI GPT-4o-mini integration with production-grade NLU pipeline.
    """

    LANGUAGE_NAMES = {"en": "English", "hi": "Hindi", "te": "Telugu"}

    def __init__(self):
        self.config = get_config()
        self.async_client = None
        self._initialized = False
        self.model = self.config.openai.model

        self._audio_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "logs", "audio",
        )
        os.makedirs(self._audio_dir, exist_ok=True)

    async def initialize(self) -> bool:
        try:
            api_key = self.config.openai.api_key
            if not api_key:
                logger.warning("OPENAI_API_KEY not set")
                return False
            if not OPENAI_AVAILABLE:
                logger.warning("openai package not installed")
                return False
            self.async_client = AsyncOpenAI(api_key=api_key)
            self._initialized = True
            logger.info(f"OpenAI service initialized: model={self.model}")
            return True
        except Exception as e:
            logger.error(f"OpenAI initialization failed: {e}")
            return False

    # ── Language detection ────────────────────────────────────────────

    @staticmethod
    def detect_language(text: str) -> str:
        if any("\u0900" <= ch <= "\u097F" for ch in text):
            return "hi"
        if any("\u0C00" <= ch <= "\u0C7F" for ch in text):
            return "te"
        return "en"

    # ── NLU intent classification (with retry) ────────────────────────

    async def classify_intent(self, text: str) -> Dict:
        """
        Classify user intent via GPT-4o-mini JSON mode.
        Returns {intent, confidence, entities}.
        Retries up to MAX_NLU_RETRIES on transient errors.
        """
        if not self._initialized:
            return {"intent": "unknown", "confidence": 0, "entities": {}}

        prompt = NLU_PROMPT.format(user_text=text.replace('"', "'"))

        for attempt in range(1, MAX_NLU_RETRIES + 1):
            try:
                resp = await self.async_client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=150,
                    temperature=0,
                    response_format={"type": "json_object"},
                )
                result = json.loads(resp.choices[0].message.content.strip())
                logger.info(
                    "[NLU] intent=%-22s confidence=%.2f  entities=%s",
                    result.get("intent", "unknown"),
                    float(result.get("confidence", 0)),
                    {k: v for k, v in (result.get("entities") or {}).items() if v},
                )
                return result
            except Exception as e:
                if attempt < MAX_NLU_RETRIES:
                    await asyncio.sleep(1.0 * attempt)
                    logger.warning("[NLU] attempt %d/%d failed: %s", attempt, MAX_NLU_RETRIES, str(e)[:80])
                else:
                    logger.error("[NLU] all %d attempts failed: %s", MAX_NLU_RETRIES, str(e)[:80])

        return {"intent": "unknown", "confidence": 0, "entities": {}}

    # ── Response generation ───────────────────────────────────────────

    async def generate_response(
        self,
        user_input: str,
        db_context: str = "",
        language: str = "en",
        conversation_history: List[Dict] = None,
    ) -> str:
        """
        Generate response using GPT-4o-mini with DB context.
        """
        if not self._initialized:
            return self._get_fallback_response(language)

        try:
            lang_name = self.LANGUAGE_NAMES.get(language, "English")
            system_prompt = SYSTEM_PROMPT.format(
                context=db_context or "(none)",
                response_language=lang_name,
            )

            messages = [{"role": "system", "content": system_prompt}]

            if conversation_history:
                for turn in conversation_history[-3:]:
                    if turn.get("user"):
                        messages.append({"role": "user", "content": turn["user"]})
                    if turn.get("bot"):
                        messages.append({"role": "assistant", "content": turn["bot"]})

            messages.append({"role": "user", "content": user_input})

            resp = await self.async_client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=200,
                temperature=0.2,
            )
            reply = resp.choices[0].message.content.strip()
            logger.info("[LLM] lang=%s  reply_chars=%d", language, len(reply))
            return reply

        except Exception as e:
            logger.error(f"OpenAI generation failed: {e}")
            return self._get_fallback_response(language)

    # ── TTS ───────────────────────────────────────────────────────────

    async def text_to_speech(self, text: str, language: str = "en") -> Optional[str]:
        if not GTTS_AVAILABLE:
            return None
        try:
            lang_code = {"en": "en", "hi": "hi", "te": "te"}.get(language, "en")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            filename = f"response_{timestamp}_{language}.mp3"
            filepath = os.path.join(self._audio_dir, filename)

            def _gen():
                tts = gTTS(text=text, lang=lang_code, slow=False)
                tts.save(filepath)
                return filepath

            result = await asyncio.to_thread(_gen)
            return result
        except Exception as e:
            logger.error(f"TTS failed: {e}")
            return None

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def get_fallback(lang: str) -> str:
        return FALLBACK.get(lang, FALLBACK["en"])

    def _get_fallback_response(self, language: str) -> str:
        return FALLBACK.get(language, FALLBACK["en"])

    async def health_check(self) -> Dict[str, Any]:
        return {
            "initialized": self._initialized,
            "model": self.model,
            "openai_available": OPENAI_AVAILABLE,
            "gtts_available": GTTS_AVAILABLE,
        }


# ── Global singleton ─────────────────────────────────────────────────

_openai_service: Optional[OpenAIService] = None


async def get_openai_service() -> OpenAIService:
    global _openai_service
    if _openai_service is None:
        _openai_service = OpenAIService()
        await _openai_service.initialize()
    return _openai_service
