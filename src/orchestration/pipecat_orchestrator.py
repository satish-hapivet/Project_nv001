import os
import sys
import uuid
import time
import asyncio
import logging
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from dotenv import load_dotenv

load_dotenv(override=True)

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import get_config
from database.db_wrapper import get_db_wrapper, DBWrapper

# Pipecat imports (graceful fallback if not installed)
PIPECAT_AVAILABLE = False
try:
    from pipecat.adapters.schemas.function_schema import FunctionSchema
    from pipecat.adapters.schemas.tools_schema import ToolsSchema
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.runner import PipelineRunner
    from pipecat.pipeline.task import PipelineParams, PipelineTask
    from pipecat.processors.aggregators.llm_context import LLMContext
    from pipecat.services.llm_service import FunctionCallParams
    from pipecat.frames.frames import LLMRunFrame, TTSSpeakFrame
    PIPECAT_AVAILABLE = True
except ImportError:
    pass

# Setup logger early
logger = logging.getLogger(__name__)

# OpenAI Service (Primary)
try:
    from services.openai_service import get_openai_service, OpenAIService, Intent
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.error("OpenAI service not available - this is required")


# ============================================================================
# DATA MODELS
# ============================================================================

class ConversationState(Enum):
    """Conversation state machine"""
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    RESPONDING = "responding"
    ERROR = "error"


@dataclass
class ConversationContext:
    """Context for a conversation session"""
    session_id: str
    speaker_name: str
    language: str
    state: ConversationState = ConversationState.IDLE
    history: List[Dict[str, str]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_activity: datetime = field(default_factory=datetime.utcnow)
    
    def add_turn(self, user_input: str, bot_response: str):
        """Add a conversation turn"""
        self.history.append({
            'user': user_input,
            'bot': bot_response,
            'timestamp': datetime.utcnow().isoformat()
        })
        self.last_activity = datetime.utcnow()
        if len(self.history) > 10:
            self.history = self.history[-10:]


@dataclass
class ProcessingResult:
    """Result of processing a user input"""
    success: bool
    response_text: str
    response_audio_path: Optional[str] = None
    language: str = 'en'
    intent: Optional[str] = None
    confidence: float = 0.0
    processing_time_ms: int = 0
    source: str = 'unknown'
    matched_faq_id: Optional[int] = None


# ============================================================================
# PIPECAT ORCHESTRATOR
# ============================================================================

class PipecatOrchestrator:
    """
    NIMS Hospital Voice Assistant Orchestrator
    
    Provides both:
    1. Full Pipecat pipeline mode (real-time streaming)
    2. Fallback mode (traditional REST API)
    
    Tools available to LLM:
    - search_faq: Search hospital FAQs
    - get_department_info: Get department details
    - get_facility_info: Get facility information
    """
    
    # Hospital system prompt
    SYSTEM_PROMPT = """You are a helpful medical assistant for NIMS Hospital in Hyderabad, India.

CRITICAL LANGUAGE RULES:
1. ALWAYS respond in the SAME LANGUAGE as the user's input
2. If user speaks Hindi, respond ONLY in Hindi
3. If user speaks Telugu, respond ONLY in Telugu  
4. If user speaks English, respond ONLY in English
5. NEVER switch languages mid-conversation

AVAILABLE TOOLS:
- search_faq: Search hospital FAQs by keywords (location, pharmacy, admission, etc.)
- get_department_info: Get department details (cardiology, emergency, etc.)
- get_facility_info: Get facility information (parking, canteen, etc.)

RESPONSE GUIDELINES:
- Be concise and patient-friendly
- For emergencies, direct to Emergency Ward (Ground Floor, 24/7)
- Include block, floor, and room numbers for locations
- Never provide medical diagnosis or treatment advice

HOSPITAL INFO:
- Address: Punjagutta, Hyderabad, Telangana - 500082
- Emergency: 24/7, Ground Floor
- Cardiology OPD: Room 106, Super Speciality Block, 9 AM - 1 PM (Mon-Sat)
- Pharmacy: Block A Lobby, 24/7
- Admission: Ground Floor, near OP Registration"""

    # Language mappings
    LANGUAGE_NAMES = {'en': 'English', 'hi': 'Hindi', 'te': 'Telugu'}
    LANGUAGE_CODES = {'en': 'en-US', 'hi': 'hi-IN', 'te': 'te-IN'}
    
    def __init__(self):
        self.config = get_config()
        self.db: Optional[DBWrapper] = None
        self.openai: Optional[OpenAIService] = None  # Primary LLM
        self.sessions: Dict[str, ConversationContext] = {}
        self._initialized = False
        self._pipecat_mode = PIPECAT_AVAILABLE
    
    async def initialize(self) -> bool:
        """Initialize all services"""
        try:
            # Database (always needed)
            self.db = await get_db_wrapper()
            
            # Primary: OpenAI GPT-4o-mini
            if OPENAI_AVAILABLE:
                self.openai = await get_openai_service()
                logger.info("OpenAI GPT-4o-mini service initialized (PRIMARY)")
            else:
                logger.error("OpenAI service is required but not available")
                return False
            
            self._initialized = True
            logger.info(f"Pipecat Orchestrator initialized (pipecat_mode={self._pipecat_mode})")
            return True
        except Exception as e:
            logger.error(f"Orchestrator initialization failed: {e}")
            return False
    
    # ========================================================================
    # SESSION MANAGEMENT
    # ========================================================================
    
    def create_session(self, speaker_name: str = None, language: str = None) -> ConversationContext:
        """Create a new conversation session"""
        session_id = str(uuid.uuid4())
        context = ConversationContext(
            session_id=session_id,
            speaker_name=speaker_name or self.config.language.speaker_name,
            language=language or self.config.language.default_language
        )
        self.sessions[session_id] = context
        logger.info(f"Session created: {session_id}")
        return context
    
    def get_session(self, session_id: str) -> Optional[ConversationContext]:
        """Get existing session"""
        return self.sessions.get(session_id)
    
    def end_session(self, session_id: str):
        """End and cleanup session"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"Session ended: {session_id}")
    
    # ========================================================================
    # PIPECAT FUNCTION TOOLS
    # ========================================================================
    
    async def _tool_search_faq(self, params: 'FunctionCallParams'):
        """Tool: Search FAQs by keywords"""
        keywords = params.arguments.get('keywords', [])
        language = params.arguments.get('language', 'en')
        
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(',')]
        
        result = await self.db.search_faq(keywords, language)
        
        if result:
            await params.result_callback(result['answer'])
        else:
            fallback = {
                'en': "I couldn't find that information. Please visit the help desk for assistance.",
                'hi': "मुझे वह जानकारी नहीं मिली। कृपया सहायता के लिए हेल्प डेस्क पर जाएं।",
                'te': "ఆ సమాచారం కనుగొనలేకపోయాను. దయచేసి సహాయం కోసం హెల్ప్ డెస్క్‌కు వెళ్ళండి."
            }
            await params.result_callback(fallback.get(language, fallback['en']))
    
    async def _tool_get_department_info(self, params: 'FunctionCallParams'):
        """Tool: Get department information"""
        department = params.arguments.get('department', '')
        language = params.arguments.get('language', 'en')
        
        result = await self.db.get_department_info([department.lower()], language)
        
        if result:
            await params.result_callback(
                f"{result['name']} is located at {result['location']}. "
                f"OPD Timings: {result['timings']}."
            )
        else:
            await params.result_callback(
                f"Department '{department}' information not found. Please check at reception."
            )
    
    async def _tool_get_facility_info(self, params: 'FunctionCallParams'):
        """Tool: Get facility information"""
        facility = params.arguments.get('facility', '')
        
        result = await self.db.get_facility_info([facility.lower()])
        
        if result:
            await params.result_callback(
                f"{result['name']} is at {result['location']}. "
                f"Timings: {result['timings']}. {result.get('description', '')}"
            )
        else:
            await params.result_callback(
                f"Facility '{facility}' not found. Please ask at the help desk."
            )
    
    def _build_tools_schema(self) -> 'ToolsSchema':
        """Build Pipecat tools schema for function calling"""
        search_faq = FunctionSchema(
            name="search_faq",
            description="Search hospital FAQs for information about locations, timings, procedures, etc.",
            properties={
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Keywords to search (e.g., ['pharmacy', 'location'])"
                },
                "language": {
                    "type": "string",
                    "enum": ["en", "hi", "te"],
                    "description": "Response language code"
                }
            },
            required=["keywords"]
        )
        
        get_department = FunctionSchema(
            name="get_department_info",
            description="Get department details like location, timings, services",
            properties={
                "department": {
                    "type": "string",
                    "description": "Department name (e.g., cardiology, emergency, icu)"
                },
                "language": {
                    "type": "string",
                    "enum": ["en", "hi", "te"]
                }
            },
            required=["department"]
        )
        
        get_facility = FunctionSchema(
            name="get_facility_info",
            description="Get facility information like parking, canteen, pharmacy",
            properties={
                "facility": {
                    "type": "string",
                    "description": "Facility name (e.g., parking, canteen, pharmacy)"
                }
            },
            required=["facility"]
        )
        
        return ToolsSchema(standard_tools=[search_faq, get_department, get_facility])
    
    # ========================================================================
    # MAIN PROCESSING PIPELINE
    # ========================================================================
    
    async def process_input(
        self,
        user_input: str,
        session_id: Optional[str] = None,
        detected_language: Optional[str] = None
    ) -> ProcessingResult:
        """
        Process text input through the pipeline.
        
        Pipeline:
        1. Get/create session
        2. Detect language
        3. Extract keywords
        4. Query database
        5. Generate response (with LLM enhancement)
        6. Generate audio
        """
        start_time = time.time()
        
        # Get or create session
        if session_id and session_id in self.sessions:
            context = self.sessions[session_id]
        else:
            context = self.create_session()
        
        context.state = ConversationState.PROCESSING
        
        try:
            # Detect language
            if detected_language:
                lang = detected_language
            elif self.openai:
                lang = self.openai.detect_language(user_input)
            else:
                lang = self._detect_language_simple(user_input)
            
            context.language = lang
            logger.info(f"Language: {lang}, Input: {user_input[:50]}...")
            
            # Check for greeting
            if self._is_greeting(user_input, lang):
                return await self._handle_greeting(context, lang, start_time)
            
            # Extract keywords and query database
            keywords = self._extract_keywords(user_input, lang)
            logger.info(f"Keywords: {keywords}")
            
            # Gather all relevant database context - search all tables
            db_context_parts = []
            
            if self.db:
                input_lower = user_input.lower()
                
                # Hospital general info
                hospital_keywords = ['hospital', 'nims', 'aspatal', 'aspataal', 'location', 'where', 'kahan', 'kidhar', 'sthan', 'jagah', 'ekkada', 'address']
                if any(kw in input_lower for kw in hospital_keywords):
                    db_context_parts.append("NIMS Hospital: Located at Punjagutta, Hyderabad, Telangana. Address: Panjagutta Main Road, Opposite Metro Pillar A1010. Contact: 040-23890000.")
                
                # Search departments table
                dept_result = await self.db.get_department_info(keywords, lang)
                if dept_result:
                    dept_info = f"Department: {dept_result['name']} - Location: {dept_result.get('location', 'main building')}, Timings: {dept_result.get('timings', 'Contact reception')}"
                    if dept_result.get('head_doctor'):
                        dept_info += f", Head Doctor: {dept_result['head_doctor']}"
                    if dept_result.get('contact'):
                        dept_info += f", Contact: {dept_result['contact']}"
                    db_context_parts.append(dept_info + ".")
                
                # Search facilities table
                facility_result = await self.db.get_facility_info(keywords)
                if facility_result:
                    fac_info = f"Facility: {facility_result['name']} - Location: {facility_result['location']}, Timings: {facility_result.get('timings', '24x7')}"
                    if facility_result.get('contact'):
                        fac_info += f", Contact: {facility_result['contact']}"
                    db_context_parts.append(fac_info + ".")
            
            db_context = " ".join(db_context_parts) if db_context_parts else ""
            logger.info(f"DB Context: {db_context[:100] if db_context else 'None'}")
            
            # Generate response using OpenAI - Always respond in user's language
            logger.info(f"=== GENERATING RESPONSE === Language: {lang}")
            
            response_text = None
            
            if self.openai:
                response_text = await self._generate_contextual_response(user_input, db_context, lang, context)
            
            # Final fallback only if no response
            if not response_text:
                response_text = self._get_fallback_response(lang)
            
            logger.info(f"=== FINAL RESPONSE === {response_text}")
            
            # Update history
            context.add_turn(user_input, response_text)
            context.state = ConversationState.RESPONDING
            
            # Generate audio (async)
            audio_path = None
            if self.openai:
                audio_path = await self.openai.text_to_speech(response_text, lang)
            
            processing_time = int((time.time() - start_time) * 1000)
            
            return ProcessingResult(
                success=True,
                response_text=response_text,
                response_audio_path=audio_path,
                language=lang,
                intent=self._classify_intent(user_input),
                confidence=0.9 if db_context else 0.7,
                processing_time_ms=processing_time,
                source='openai',
                matched_faq_id=None
            )
            
        except Exception as e:
            logger.error(f"Processing error: {e}")
            context.state = ConversationState.ERROR
            return ProcessingResult(
                success=False,
                response_text=self._get_error_response(context.language),
                language=context.language,
                processing_time_ms=int((time.time() - start_time) * 1000),
                source='error'
            )
    
    async def process_voice_input(
        self,
        audio_bytes: bytes,
        session_id: Optional[str] = None,
        language_hint: Optional[str] = None
    ) -> ProcessingResult:
        """
        Process voice input: STT → Process → TTS
        """
        start_time = time.time()
        
        # Get or create session
        if session_id and session_id in self.sessions:
            context = self.sessions[session_id]
            language_hint = language_hint or context.language
        else:
            context = self.create_session()
        
        context.state = ConversationState.LISTENING
        
        try:
            # Speech-to-Text
            if not self.speech:
                return ProcessingResult(
                    success=False,
                    response_text="Voice recognition not available. Please use text.",
                    language=language_hint or 'en',
                    processing_time_ms=int((time.time() - start_time) * 1000),
                    source='error'
                )
            
            transcribed_text, detected_lang, confidence = await self.speech.transcribe_audio_bytes(
                audio_bytes, sample_rate=16000, language_hint=language_hint
            )
            
            if not transcribed_text:
                return ProcessingResult(
                    success=False,
                    response_text=self._get_no_speech_response(language_hint or 'en'),
                    language=language_hint or 'en',
                    processing_time_ms=int((time.time() - start_time) * 1000),
                    source='stt_failed'
                )
            
            logger.info(f"STT: '{transcribed_text}' (lang={detected_lang})")
            
            # Process transcribed text
            result = await self.process_input(
                user_input=transcribed_text,
                session_id=context.session_id,
                detected_language=detected_lang
            )
            
            result.processing_time_ms = int((time.time() - start_time) * 1000)
            return result
            
        except Exception as e:
            logger.error(f"Voice processing error: {e}")
            return ProcessingResult(
                success=False,
                response_text=self._get_error_response(language_hint or 'en'),
                language=language_hint or 'en',
                processing_time_ms=int((time.time() - start_time) * 1000),
                source='error'
            )
    
    # ========================================================================
    # HELPER METHODS
    # ========================================================================
    
    def _detect_language_simple(self, text: str) -> str:
        """Simple language detection based on character ranges"""
        for char in text:
            if '\u0900' <= char <= '\u097F':  # Devanagari (Hindi)
                return 'hi'
            if '\u0C00' <= char <= '\u0C7F':  # Telugu
                return 'te'
        return 'en'
    
    def _is_greeting(self, text: str, lang: str) -> bool:
        """Check if input is a greeting"""
        greetings = {
            'en': ['hi', 'hello', 'hey', 'good morning', 'good afternoon', 'good evening'],
            'hi': ['नमस्ते', 'हैलो', 'हाय', 'नमस्कार'],
            'te': ['హలో', 'హాయ్', 'నమస్కారం', 'నమస్తే']
        }
        text_lower = text.lower().strip()
        return any(g in text_lower for g in greetings.get(lang, greetings['en']))
    
    async def _handle_greeting(self, context: ConversationContext, lang: str, start_time: float) -> ProcessingResult:
        """Handle greeting responses"""
        greetings = {
            'en': "Hello! Welcome to NIMS Hospital. How can I help you today? You can ask about departments, facilities, or directions.",
            'hi': "नमस्ते! NIMS अस्पताल में आपका स्वागत है। मैं आज आपकी कैसे मदद कर सकता हूं? आप विभागों, सुविधाओं या दिशाओं के बारे में पूछ सकते हैं।",
            'te': "హలో! NIMS హాస్పిటల్‌కు స్వాగతం. నేను మీకు ఎలా సహాయం చేయగలను? మీరు విభాగాలు, సౌకర్యాలు లేదా దిశలు గురించి అడగవచ్చు."
        }
        
        response = greetings.get(lang, greetings['en'])
        audio_path = None
        
        if self.openai:
            audio_path = await self.openai.text_to_speech(response, lang)
        
        context.add_turn("greeting", response)
        
        return ProcessingResult(
            success=True,
            response_text=response,
            response_audio_path=audio_path,
            language=lang,
            intent='greeting',
            confidence=1.0,
            processing_time_ms=int((time.time() - start_time) * 1000),
            source='greeting'
        )
    
    def _extract_keywords(self, text: str, lang: str) -> List[str]:
        """Extract search keywords from text"""
        # Keyword mappings for medical/hospital terms
        keyword_map = {
            # Departments
            'cardiology': ['cardiology', 'heart', 'cardiac', 'chest', 'cardiologist', 'dil'],
            'emergency': ['emergency', 'urgent', 'accident', 'trauma', 'apatkal'],
            'orthopedics': ['orthopedics', 'ortho', 'bone', 'fracture', 'haddi'],
            'neurology': ['neurology', 'neuro', 'brain', 'nerve', 'dimag'],
            'pediatrics': ['pediatrics', 'child', 'children', 'baby', 'bachcha'],
            'gynecology': ['gynecology', 'gynaecology', 'women', 'pregnancy', 'mahila'],
            # Facilities  
            'pharmacy': ['pharmacy', 'medicine', 'drug', 'medical shop', 'dawai', 'dawakhana'],
            'parking': ['parking', 'park', 'vehicle', 'car', 'bike', 'gaadi'],
            'canteen': ['canteen', 'food', 'cafeteria', 'restaurant', 'eat', 'khana', 'bhojan'],
            'admission': ['admission', 'admit', 'bed', 'ward', 'dakhil'],
            'atm': ['atm', 'cash', 'bank', 'money', 'paisa'],
            # Hospital general
            'hospital': ['hospital', 'aspatal', 'aspataal', 'nims'],
            # General queries
            'timing': ['timing', 'time', 'hours', 'open', 'close', 'when', 'kab', 'samay'],
            'location': ['where', 'location', 'located', 'find', 'direction', 'kahan', 'kidhar', 'sthan', 'jagah', 'ekkada', 'ekkadi'],
            'doctor': ['doctor', 'dr', 'physician', 'specialist', 'daktar', 'vaidya'],
        }
        
        text_lower = text.lower()
        keywords = []
        
        for key, variants in keyword_map.items():
            if any(v in text_lower for v in variants):
                keywords.append(key)
        
        # Add raw words as fallback (skip common words)
        stop_words = ['the', 'is', 'are', 'in', 'at', 'to', 'for', 'of', 'and', 'hai', 'ka', 'ki', 'ke', 'mein', 'undi']
        words = [w.strip('?.,!') for w in text_lower.split() if len(w) > 2 and w not in stop_words]
        keywords.extend([w for w in words[:5] if w not in keywords])
        
        return keywords[:10]
    
    def _classify_intent(self, text: str) -> str:
        """Simple intent classification"""
        text_lower = text.lower()
        
        if any(w in text_lower for w in ['where', 'location', 'find', 'ఎక్కడ', 'कहां']):
            return 'location_query'
        if any(w in text_lower for w in ['time', 'timing', 'when', 'hours', 'समय', 'సమయం']):
            return 'timing_query'
        if any(w in text_lower for w in ['emergency', 'urgent', 'accident']):
            return 'emergency'
        return 'general_info'
    
    async def _generate_llm_response(self, user_input: str, lang: str, context: ConversationContext) -> str:
        """Generate response using OpenAI LLM"""
        try:
            # Use OpenAI GPT-4o-mini
            if self.openai:
                history = [{'user': turn['user'], 'bot': turn['assistant']} for turn in context.history[-3:]]
                response = await self.openai.generate_response(
                    user_input=user_input,
                    db_context="",
                    language=lang,
                    conversation_history=history
                )
                return response
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
        
        return self._get_fallback_response(lang)
    
    async def _generate_contextual_response(self, user_input: str, db_context: str, lang: str, context: ConversationContext) -> str:
        """Generate natural response using database context"""
        try:
            # Use OpenAI GPT-4o-mini
            if self.openai:
                # Format history as list of dicts with 'user' and 'bot' keys
                history = [{'user': turn['user'], 'bot': turn['assistant']} for turn in context.history[-3:]]
                response = await self.openai.generate_response(
                    user_input=user_input,
                    db_context=db_context,
                    language=lang,
                    conversation_history=history
                )
                return response
        except Exception as e:
            logger.error(f"Contextual LLM generation failed: {e}")
        
        # Fallback to raw database context
        return db_context if db_context else self._get_fallback_response(lang)

    def _get_fallback_response(self, lang: str) -> str:
        """Get fallback response"""
        fallbacks = {
            'en': "I couldn't find that information. Please visit the help desk near the main entrance for assistance.",
            'hi': "मुझे वह जानकारी नहीं मिली। कृपया सहायता के लिए मुख्य प्रवेश द्वार के पास हेल्प डेस्क पर जाएं।",
            'te': "ఆ సమాచారం కనుగొనలేకపోయాను. దయచేసి సహాయం కోసం ప్రధాన ప్రవేశం వద్ద హెల్ప్ డెస్క్‌కు వెళ్ళండి."
        }
        return fallbacks.get(lang, fallbacks['en'])
    
    def _get_error_response(self, lang: str) -> str:
        """Get error response"""
        errors = {
            'en': "I apologize, but I encountered an error. Please try again or visit the help desk.",
            'hi': "मुझे खेद है, एक त्रुटि हुई। कृपया पुनः प्रयास करें या हेल्प डेस्क पर जाएं।",
            'te': "క్షమించండి, తప్పు జరిగింది. దయచేసి మళ్ళీ ప్రయత్నించండి లేదా హెల్ప్ డెస్క్‌కు వెళ్ళండి."
        }
        return errors.get(lang, errors['en'])
    
    def _get_no_speech_response(self, lang: str) -> str:
        """Get no speech detected response"""
        responses = {
            'en': "I couldn't hear you clearly. Please speak again.",
            'hi': "मैं आपको स्पष्ट रूप से नहीं सुन सका। कृपया फिर से बोलें।",
            'te': "నేను మిమ్మల్ని స్పష్టంగా వినలేకపోయాను. దయచేసి మళ్ళీ మాట్లాడండి."
        }
        return responses.get(lang, responses['en'])
    
    # ========================================================================
    # HEALTH CHECK
    # ========================================================================
    
    async def health_check(self) -> Dict[str, Any]:
        """Return health status"""
        db_health = await self.db.health_check() if self.db else {'status': 'not_initialized'}
        
        openai_health = {'status': 'not_initialized'}
        if self.openai:
            try:
                openai_health = await self.openai.health_check()
            except Exception as e:
                openai_health = {'status': 'error', 'message': str(e)}
        
        return {
            'orchestrator': 'healthy' if self._initialized else 'unhealthy',
            'active_sessions': len(self.sessions),
            'pipecat_mode': self._pipecat_mode,
            'database': db_health,
            'openai': openai_health,
            'timestamp': datetime.utcnow().isoformat()
        }


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

_orchestrator: Optional[PipecatOrchestrator] = None


async def get_orchestrator() -> PipecatOrchestrator:
    """Get or create the global orchestrator instance"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = PipecatOrchestrator()
        await _orchestrator.initialize()
    return _orchestrator


# ============================================================================
# STANDALONE TEST
# ============================================================================

if __name__ == "__main__":
    async def test():
        print("Testing Pipecat Orchestrator...")
        
        orchestrator = PipecatOrchestrator()
        await orchestrator.initialize()
        
        # Test English
        result = await orchestrator.process_input("Where is the pharmacy?")
        print(f"\nEN: {result.response_text}")
        
        # Test Hindi
        result = await orchestrator.process_input("दवाखाना कहाँ है?")
        print(f"HI: {result.response_text}")
        
        # Test Telugu
        result = await orchestrator.process_input("ఫార్మసీ ఎక్కడ ఉంది?")
        print(f"TE: {result.response_text}")
        
        print("\n✅ Tests completed")
    
    asyncio.run(test())
