"""
NIMS Hospital Voice Assistant — Orchestrator
----------------------------------------------
Production-grade pipeline ported from voice_agent:
  1. Language detection
  2. NLU intent classification (GPT-4o-mini, 12 intents)
  3. DB context fetching (6 tables)
  4. LLM response generation (context-aware, same-language)
  5. TTS audio generation

Follows Project_nv001 clean architecture:
  main.py (Presentation) → orchestrator (Use Cases) → db_wrapper + openai_service (Infrastructure)
"""
import uuid
import time
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import get_config
from database.db_wrapper import get_db_wrapper, DBWrapper
from services.openai_service import get_openai_service, OpenAIService, NLU_CONFIDENCE_THRESHOLD
from services.stt_service import get_stt_service, STTService, STTResult
from services.tts_service import get_tts_service, TTSService
from services.hallucination_filter import is_valid_transcript

logger = logging.getLogger(__name__)


# ============================================================================
# DATA MODELS
# ============================================================================

class ConversationState(Enum):
    IDLE = "idle"
    PROCESSING = "processing"
    RESPONDING = "responding"
    ERROR = "error"


@dataclass
class ConversationContext:
    session_id: str
    language: str = "en"
    state: ConversationState = ConversationState.IDLE
    history: List[Dict[str, str]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_activity: datetime = field(default_factory=datetime.utcnow)

    def add_turn(self, user_input: str, bot_response: str):
        self.history.append({
            "user": user_input,
            "bot": bot_response,
            "timestamp": datetime.utcnow().isoformat(),
        })
        self.last_activity = datetime.utcnow()
        if len(self.history) > 10:
            self.history = self.history[-10:]


@dataclass
class ProcessingResult:
    success: bool
    response_text: str
    response_audio_path: Optional[str] = None
    language: str = "en"
    intent: Optional[str] = None
    confidence: float = 0.0
    processing_time_ms: int = 0
    source: str = "unknown"


# ============================================================================
# ORCHESTRATOR
# ============================================================================

class PipecatOrchestrator:
    """
    NIMS Hospital Voice Assistant Orchestrator.

    Pipeline for every user query:
      detect language → classify intent (NLU) → fetch DB context → generate LLM response → TTS
    """

    def __init__(self):
        self.config = get_config()
        self.db: Optional[DBWrapper] = None
        self.openai: Optional[OpenAIService] = None
        self.stt: Optional[STTService] = None
        self.tts: Optional[TTSService] = None
        self.sessions: Dict[str, ConversationContext] = {}
        self._initialized = False

    async def initialize(self) -> bool:
        try:
            self.db = await get_db_wrapper()
            self.openai = await get_openai_service()
            if not self.openai or not self.openai._initialized:
                logger.error("OpenAI service failed to initialize")
                return False

            # Initialize STT (may fail on machines without model — non-fatal)
            try:
                self.stt = await get_stt_service(
                    model_size=self.config.stt.model_size,
                    device=self.config.stt.device,
                )
                logger.info("STT service initialized")
            except Exception as e:
                logger.warning("STT service unavailable (text-only mode): %s", e)
                self.stt = None

            # Initialize TTS (edge-tts)
            try:
                self.tts = await get_tts_service()
                logger.info("TTS service initialized (edge-tts)")
            except Exception as e:
                logger.warning("TTS service unavailable: %s", e)
                self.tts = None

            self._initialized = True
            logger.info("Orchestrator initialized (NLU pipeline active)")
            return True
        except Exception as e:
            logger.error(f"Orchestrator init failed: {e}")
            return False

    # ====================================================================
    # SESSION MANAGEMENT
    # ====================================================================

    def create_session(self, language: str = None) -> ConversationContext:
        session_id = str(uuid.uuid4())
        ctx = ConversationContext(
            session_id=session_id,
            language=language or self.config.language.default_language,
        )
        self.sessions[session_id] = ctx
        logger.info(f"Session created: {session_id}")
        return ctx

    def get_session(self, session_id: str) -> Optional[ConversationContext]:
        return self.sessions.get(session_id)

    def end_session(self, session_id: str):
        if session_id in self.sessions:
            del self.sessions[session_id]

    # ====================================================================
    # MAIN PIPELINE
    # ====================================================================

    async def process_input(
        self,
        user_input: str,
        session_id: Optional[str] = None,
        detected_language: Optional[str] = None,
    ) -> ProcessingResult:
        """
        Full pipeline: text → NLU → DB → LLM → TTS.
        """
        start_time = time.time()

        # Session
        if session_id and session_id in self.sessions:
            ctx = self.sessions[session_id]
        else:
            ctx = self.create_session()

        ctx.state = ConversationState.PROCESSING

        try:
            # 1 ─ Language detection
            lang = detected_language or self.openai.detect_language(user_input)
            ctx.language = lang
            logger.info(f"[Pipeline] lang={lang}  input={user_input[:60]}...")

            # 2 ─ NLU intent classification
            nlu = await self.openai.classify_intent(user_input)
            intent_name = nlu.get("intent", "unknown")
            confidence = float(nlu.get("confidence", 0))

            # Low confidence → fallback
            if confidence < NLU_CONFIDENCE_THRESHOLD:
                fallback_text = self.openai.get_fallback(lang)
                audio_path = await self._generate_tts(fallback_text, lang)
                ctx.add_turn(user_input, fallback_text)
                return ProcessingResult(
                    success=True,
                    response_text=fallback_text,
                    response_audio_path=audio_path,
                    language=lang,
                    intent=intent_name,
                    confidence=confidence,
                    processing_time_ms=int((time.time() - start_time) * 1000),
                    source="fallback",
                )

            # 3 ─ Fetch DB context
            db_context = await self._fetch_context(nlu)
            logger.info(f"[Pipeline] intent={intent_name}  context_chars={len(db_context)}")

            # 4 ─ LLM response generation
            history = [{"user": t["user"], "bot": t["bot"]} for t in ctx.history[-3:]]
            response_text = await self.openai.generate_response(
                user_input=user_input,
                db_context=db_context,
                language=lang,
                conversation_history=history,
            )

            if not response_text:
                response_text = self.openai.get_fallback(lang)

            # 5 ─ TTS (edge-tts, fallback to gTTS)
            audio_path = await self._generate_tts(response_text, lang)

            ctx.add_turn(user_input, response_text)
            ctx.state = ConversationState.RESPONDING

            return ProcessingResult(
                success=True,
                response_text=response_text,
                response_audio_path=audio_path,
                language=lang,
                intent=intent_name,
                confidence=confidence,
                processing_time_ms=int((time.time() - start_time) * 1000),
                source="nlu_pipeline",
            )

        except Exception as e:
            logger.error(f"Pipeline error: {e}", exc_info=True)
            ctx.state = ConversationState.ERROR
            err_text = self._error_response(ctx.language)
            return ProcessingResult(
                success=False,
                response_text=err_text,
                language=ctx.language,
                processing_time_ms=int((time.time() - start_time) * 1000),
                source="error",
            )

    # ====================================================================
    # TTS HELPER (edge-tts primary, gTTS fallback)
    # ====================================================================

    async def _generate_tts(self, text: str, lang: str) -> Optional[str]:
        """Generate TTS audio file. Tries edge-tts first, falls back to gTTS."""
        if self.tts:
            path = await self.tts.generate_file(text, lang)
            if path:
                return path
        # Fallback to gTTS via openai_service
        return await self.openai.text_to_speech(text, lang)

    # ====================================================================
    # AUDIO PIPELINE: audio bytes → STT → NLU → DB → LLM → TTS
    # ====================================================================

    async def process_audio_input(
        self,
        audio_bytes: bytes,
        session_id: Optional[str] = None,
        language_hint: Optional[str] = None,
    ) -> ProcessingResult:
        """
        Full voice pipeline: raw PCM audio → STT → hallucination filter
        → NLU → DB → LLM → TTS.

        Args:
            audio_bytes:   Raw PCM int16 audio at 16 kHz mono.
            language_hint: Optional ISO 639-1 code to force language.
            session_id:    Existing session or new one created.
        """
        start_time = time.time()

        if not self.stt or not self.stt._initialized:
            return ProcessingResult(
                success=False,
                response_text="Speech recognition is not available.",
                processing_time_ms=int((time.time() - start_time) * 1000),
                source="error",
            )

        # Session
        if session_id and session_id in self.sessions:
            ctx = self.sessions[session_id]
        else:
            ctx = self.create_session()

        ctx.state = ConversationState.PROCESSING

        try:
            # 1 ─ STT: audio → text
            stt_result: STTResult = await self.stt.transcribe(
                audio_bytes, language_hint=language_hint,
            )

            if not stt_result.text.strip() or not stt_result.is_confident:
                fallback = self.openai.get_fallback(stt_result.language or "en")
                audio_path = await self._generate_tts(fallback, stt_result.language or "en")
                return ProcessingResult(
                    success=True,
                    response_text=fallback,
                    response_audio_path=audio_path,
                    language=stt_result.language or "en",
                    confidence=0.0,
                    processing_time_ms=int((time.time() - start_time) * 1000),
                    source="stt_low_confidence",
                )

            # 2 ─ Hallucination filter
            is_valid, reason = is_valid_transcript(stt_result.text)
            if not is_valid:
                logger.info("[Pipeline] Hallucination rejected: %s", reason)
                fallback = self.openai.get_fallback(stt_result.language)
                audio_path = await self._generate_tts(fallback, stt_result.language)
                return ProcessingResult(
                    success=True,
                    response_text=fallback,
                    response_audio_path=audio_path,
                    language=stt_result.language,
                    confidence=0.0,
                    processing_time_ms=int((time.time() - start_time) * 1000),
                    source="hallucination_rejected",
                )

            # 3 ─ Feed transcribed text into the existing NLU pipeline
            return await self.process_input(
                user_input=stt_result.text,
                session_id=ctx.session_id,
                detected_language=stt_result.language,
            )

        except Exception as e:
            logger.error(f"Audio pipeline error: {e}", exc_info=True)
            ctx.state = ConversationState.ERROR
            err_text = self._error_response(ctx.language)
            return ProcessingResult(
                success=False,
                response_text=err_text,
                language=ctx.language,
                processing_time_ms=int((time.time() - start_time) * 1000),
                source="error",
            )

    # ====================================================================
    # DB CONTEXT FETCHING — 12 intents, 6 tables
    # ====================================================================

    async def _fetch_context(self, nlu: Dict) -> str:
        """
        Maps NLU intent + entities → DB queries → plain-text context for LLM.
        Mirrors the proven voice_agent _fetch_context() logic.
        """
        ents = nlu.get("entities") or {}
        intent = nlu.get("intent", "unknown")
        today = date.today()

        try:
            # ── find_doctor ──────────────────────────────────────────
            if intent == "find_doctor":
                keyword = ents.get("doctor_name") or ""
                dept_key = ents.get("dept_name") or ""

                if keyword:
                    rows = await self.db.find_doctors_by_keyword(keyword)
                elif dept_key:
                    rows = await self.db.find_doctors_by_specialization(dept_key)
                    if not rows:
                        rows = await self.db.find_doctors_by_department(dept_key)
                else:
                    rows = []

                if not rows:
                    rows = await self.db.find_available_doctors()

                if rows:
                    lines = [self._doctor_context(d) for d in rows[:5]]
                    return "Doctors found:\n" + "\n".join(lines)

            # ── find_department ───────────────────────────────────────
            elif intent == "find_department":
                keyword = ents.get("dept_name") or ""
                if keyword:
                    dept = await self.db.find_department_by_name(keyword)
                    if dept:
                        ctx = self._department_context(dept)
                        docs = await self.db.find_doctors_by_department(keyword)
                        if docs:
                            ctx += "\nDoctors in this department:\n"
                            ctx += "\n".join(self._doctor_context(d) for d in docs[:5])
                        return ctx
                depts = await self.db.list_departments()
                if depts:
                    return "Available departments: " + ", ".join(d["name"] for d in depts[:8]) + "."

            # ── find_ward ────────────────────────────────────────────
            elif intent == "find_ward":
                dept_key = ents.get("dept_name") or ""
                ward_type = ents.get("ward_type") or ""

                if ward_type:
                    rows = await self.db.find_wards_by_type(ward_type)
                elif dept_key:
                    rows = await self.db.find_wards_by_department(dept_key)
                else:
                    rows = await self.db.find_available_wards()

                if rows:
                    lines = [self._ward_context(w) for w in rows[:6]]
                    return "Wards found:\n" + "\n".join(lines)

            # ── find_nurse ───────────────────────────────────────────
            elif intent == "find_nurse":
                dept_key = ents.get("dept_name") or ""
                if dept_key:
                    rows = await self.db.find_nurses_by_department(dept_key)
                else:
                    rows = await self.db.list_nurses()
                if rows:
                    lines = [self._nurse_context(n) for n in rows[:6]]
                    return "Nurses found:\n" + "\n".join(lines)

            # ── check_appointment ────────────────────────────────────
            elif intent == "check_appointment":
                patient = ents.get("patient_name") or ""
                appt_date_str = ents.get("date") or today.isoformat()
                if patient:
                    try:
                        appt_date = date.fromisoformat(appt_date_str)
                    except (ValueError, TypeError):
                        appt_date = today
                    row = await self.db.find_appointment_by_patient_and_date(patient, appt_date)
                    if not row:
                        row = await self.db.find_appointment_by_patient(patient)
                    if row:
                        return self._appointment_context(row)

            # ── book_appointment ─────────────────────────────────────
            elif intent == "book_appointment":
                patient = ents.get("patient_name") or ""
                phone = ents.get("patient_phone") or ""
                doctor_name = ents.get("doctor_name") or ""
                appt_date_str = ents.get("date") or ""
                appt_time = ents.get("time") or ""

                if not patient or not doctor_name or not appt_date_str or not appt_time:
                    missing = []
                    if not patient:
                        missing.append("patient name")
                    if not doctor_name:
                        missing.append("doctor name")
                    if not appt_date_str:
                        missing.append("date")
                    if not appt_time:
                        missing.append("time")
                    return f"To book an appointment I need: {', '.join(missing)}."

                # Find the doctor
                doc = await self.db.find_doctor_by_name(doctor_name)
                if not doc:
                    return f"Could not find a doctor matching '{doctor_name}'. Please check the name."

                try:
                    appt_date = date.fromisoformat(appt_date_str)
                except (ValueError, TypeError):
                    return "Invalid date format. Please provide the date as YYYY-MM-DD."

                result = await self.db.create_appointment(
                    patient_name=patient,
                    patient_phone=phone,
                    doctor_id=doc["doctor_id"],
                    appointment_date=appt_date,
                    appointment_time=appt_time,
                )

                if result["success"]:
                    return (
                        f"Appointment booked: {patient} with Dr. {doc['name']} ({doc['specialization']}) "
                        f"on {appt_date.strftime('%d %b %Y')} at {appt_time}. "
                        f"Appointment ID: {result['appointment_id']}."
                    )
                else:
                    return result["message"]

            # ── emergency ────────────────────────────────────────────
            elif intent == "emergency":
                info = await self.db.get_hospital_info()
                parts = []
                if info.get("emergency_location"):
                    parts.append(f"Emergency Ward: {info['emergency_location']}")
                if info.get("emergency_hours"):
                    parts.append(f"open {info['emergency_hours']}")
                if info.get("emergency_phone"):
                    parts.append(f"Phone: {info['emergency_phone']}")
                if info.get("ambulance_number"):
                    parts.append(f"Ambulance: {info['ambulance_number']}")
                return ", ".join(parts) + "." if parts else ""

            # ── greeting ─────────────────────────────────────────────
            elif intent == "greeting":
                info = await self.db.get_hospital_info()
                parts = []
                if info.get("name"):
                    addr = f", {info.get('address', '')}" if info.get("address") else ""
                    parts.append(f"Welcome to {info['name']}{addr}.")
                if info.get("opd_hours"):
                    parts.append(f"OPD: {info['opd_hours']}.")
                if info.get("emergency_hours"):
                    parts.append(f"Emergency services available {info['emergency_hours']}.")
                return " ".join(parts)

            # ── hospital_info ────────────────────────────────────────
            elif intent == "hospital_info":
                info = await self.db.get_hospital_info()
                parts = []
                if info.get("name"):
                    addr = f", {info.get('address', '')}" if info.get("address") else ""
                    parts.append(f"{info['name']}{addr}.")
                if info.get("phone"):
                    parts.append(f"Phone: {info['phone']}.")
                if info.get("opd_hours"):
                    parts.append(f"OPD: {info['opd_hours']}.")
                if info.get("visiting_hours"):
                    parts.append(f"Visiting hours: {info['visiting_hours']}.")
                if info.get("icu_visiting"):
                    parts.append(f"ICU visiting: {info['icu_visiting']}.")
                return " ".join(parts)

            # ── pharmacy ─────────────────────────────────────────────
            elif intent == "pharmacy":
                info = await self.db.get_hospital_info()
                parts = []
                if info.get("pharmacy_location"):
                    parts.append(f"Pharmacy: {info['pharmacy_location']}")
                if info.get("pharmacy_hours"):
                    parts.append(f"Hours: {info['pharmacy_hours']}")
                return ", ".join(parts) + "." if parts else ""

            # ── facilities ───────────────────────────────────────────
            elif intent == "facilities":
                info = await self.db.get_hospital_info()
                keys = ["parking", "cafeteria", "atm", "blood_bank", "lab", "billing"]
                parts = []
                for k in keys:
                    v = info.get(k)
                    if v:
                        parts.append(f"{k.replace('_', ' ').title()}: {v}")
                return ". ".join(parts) + "." if parts else ""

        except Exception as e:
            logger.error(f"[Context] DB error: {e}")

        return ""

    # ====================================================================
    # CONTEXT FORMATTERS
    # ====================================================================

    @staticmethod
    def _doctor_context(d: Dict) -> str:
        parts = [
            f"{d['name']} ({d['specialization']})",
            f"- {d.get('availability', 'Available')}",
            f"Floor {d.get('floor', '?')}, Room {d.get('room_no', '?')}",
        ]
        if d.get("dept_name"):
            parts.append(f"Dept: {d['dept_name']}")
        if d.get("available_days") and d.get("available_time"):
            parts.append(f"Hours: {d['available_days']} {d['available_time']}")
        if d.get("consultation_fee"):
            parts.append(f"Fee: Rs.{d['consultation_fee']}")
        return ", ".join(parts) + "."

    @staticmethod
    def _department_context(d: Dict) -> str:
        parts = [f"{d['name']} department is on Floor {d.get('floor', '?')}, Room {d.get('room_no', '?')}."]
        if d.get("description"):
            parts.append(f"Services: {d['description']}.")
        if d.get("phone_ext"):
            parts.append(f"Extension: {d['phone_ext']}.")
        return " ".join(parts)

    @staticmethod
    def _ward_context(w: Dict) -> str:
        parts = [
            f"{w['name']} ({w.get('ward_type', 'General')})",
            f"Floor {w.get('floor', '?')}",
            f"Beds: {w.get('available_beds', '?')}/{w.get('total_beds', '?')} available",
        ]
        if w.get("dept_name"):
            parts.append(f"Dept: {w['dept_name']}")
        return ", ".join(parts) + "."

    @staticmethod
    def _nurse_context(n: Dict) -> str:
        parts = [f"{n['name']} ({n.get('shift', 'Day')} shift)"]
        if n.get("ward_name"):
            parts.append(f"Ward: {n['ward_name']}")
        if n.get("dept_name"):
            parts.append(f"Dept: {n['dept_name']}")
        return ", ".join(parts) + "."

    @staticmethod
    def _appointment_context(a: Dict) -> str:
        appt_date = a.get("appointment_date", "")
        if isinstance(appt_date, date):
            appt_date = appt_date.strftime("%d %b %Y")
        parts = [
            f"Appointment for {a['patient_name']}",
            f"with {a.get('doctor_name', '')}" if a.get("doctor_name") else "",
            f"on {appt_date} at {a.get('appointment_time', '')}",
            f"Status: {a.get('status', 'Scheduled')}",
        ]
        return " ".join(p for p in parts if p) + "."

    # ====================================================================
    # ERROR HELPERS
    # ====================================================================

    @staticmethod
    def _error_response(lang: str) -> str:
        errors = {
            "en": "I apologize, but I encountered an error. Please try again or visit the help desk.",
            "hi": "मुझे खेद है, एक त्रुटि हुई। कृपया पुनः प्रयास करें या हेल्प डेस्क पर जाएं।",
            "te": "క్షమించండి, తప్పు జరిగింది. దయచేసి మళ్ళీ ప్రయత్నించండి లేదా హెల్ప్ డెస్క్‌కు వెళ్ళండి.",
        }
        return errors.get(lang, errors["en"])

    # ====================================================================
    # HEALTH CHECK
    # ====================================================================

    async def health_check(self) -> Dict[str, Any]:
        db_health = await self.db.health_check() if self.db else {"status": "not_initialized"}
        openai_health = {"status": "not_initialized"}
        if self.openai:
            try:
                openai_health = await self.openai.health_check()
            except Exception as e:
                openai_health = {"status": "error", "message": str(e)}
        stt_health = await self.stt.health_check() if self.stt else {"status": "not_available"}
        tts_health = await self.tts.health_check() if self.tts else {"status": "not_available"}
        return {
            "orchestrator": "healthy" if self._initialized else "unhealthy",
            "active_sessions": len(self.sessions),
            "database": db_health,
            "openai": openai_health,
            "stt": stt_health,
            "tts": tts_health,
            "timestamp": datetime.utcnow().isoformat(),
        }


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

_orchestrator: Optional[PipecatOrchestrator] = None


async def get_orchestrator() -> PipecatOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = PipecatOrchestrator()
        await _orchestrator.initialize()
    return _orchestrator
