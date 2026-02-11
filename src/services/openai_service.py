"""
OpenAI GPT-4o-mini Service for NIMS Hospital Voice Assistant
Provides: Text Generation, Language Detection
Supports: English, Hindi, Telugu with strict same-language responses
"""
import logging
import os
import sys
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum

# OpenAI imports
try:
    from openai import OpenAI, AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = None
    AsyncOpenAI = None

# TTS fallback
try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import get_config

logger = logging.getLogger(__name__)


class Intent(Enum):
    """User intent classification"""
    GREETING = "greeting"
    LOCATION_QUERY = "location_query"
    TIMING_QUERY = "timing_query"
    DEPARTMENT_QUERY = "department_query"
    FACILITY_QUERY = "facility_query"
    ADMISSION_QUERY = "admission_query"
    INSURANCE_QUERY = "insurance_query"
    EMERGENCY = "emergency"
    GENERAL_INFO = "general_info"
    UNKNOWN = "unknown"


class OpenAIService:
    """
    OpenAI GPT-4o-mini Integration for hospital voice assistant
    - Text generation with context
    - Language detection and matching
    - TTS via gTTS fallback
    """
    
    LANGUAGE_NAMES = {
        'en': 'English',
        'hi': 'Hindi', 
        'te': 'Telugu'
    }
    
    LANGUAGE_CODES = {
        'en': 'en-US',
        'hi': 'hi-IN',
        'te': 'te-IN'
    }
    
    # System prompt for hospital assistant
    SYSTEM_PROMPT = """You are a helpful voice assistant for NIMS Hospital in Hyderabad, India.

CRITICAL LANGUAGE RULES (MUST FOLLOW):
1. ALWAYS respond in the EXACT SAME LANGUAGE as the user's question
2. If user asks in Hindi (हिंदी), respond ONLY in Hindi using Devanagari script
3. If user asks in Telugu (తెలుగు), respond ONLY in Telugu using Telugu script  
4. If user asks in English, respond ONLY in English
5. NEVER mix languages in your response

RESPONSE GUIDELINES:
1. Be CONCISE - give SHORT, DIRECT answers (1-3 sentences max)
2. Answer ONLY what the user asked - no extra information
3. Use the database context provided to give accurate information
4. If information is missing, suggest visiting the help desk

You help with: Department locations, Facility info (pharmacy, parking), Hospital services."""

    def __init__(self):
        self.config = get_config()
        self.client = None
        self.async_client = None
        self._initialized = False
        self.model = "gpt-4o-mini"
        
        self._audio_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            'logs', 'audio'
        )
        os.makedirs(self._audio_dir, exist_ok=True)
    
    async def initialize(self) -> bool:
        """Initialize OpenAI client"""
        try:
            api_key = os.getenv('OPENAI_API_KEY', '')
            
            if not api_key:
                logger.warning("OPENAI_API_KEY not set - service will not be available")
                return False
            
            if not OPENAI_AVAILABLE:
                logger.warning("OpenAI package not installed")
                return False
            
            self.client = OpenAI(api_key=api_key)
            self.async_client = AsyncOpenAI(api_key=api_key)
            self._initialized = True
            
            logger.info(f"OpenAI service initialized with model: {self.model}")
            return True
            
        except Exception as e:
            logger.error(f"OpenAI initialization failed: {e}")
            return False
    
    def detect_language(self, text: str) -> str:
        """Detect language from text"""
        # Check for Hindi characters
        if any('\u0900' <= char <= '\u097F' for char in text):
            return 'hi'
        # Check for Telugu characters
        if any('\u0C00' <= char <= '\u0C7F' for char in text):
            return 'te'
        return 'en'
    
    async def generate_response(
        self,
        user_input: str,
        db_context: str = "",
        language: str = "en",
        conversation_history: List[Dict] = None
    ) -> str:
        """
        Generate response using GPT-4o-mini
        
        Args:
            user_input: User's question
            db_context: Database context (department/facility info)
            language: Target response language
            conversation_history: Previous conversation turns
        
        Returns:
            Generated response text
        """
        if not self._initialized:
            logger.warning("OpenAI not initialized")
            return self._get_fallback_response(language)
        
        try:
            lang_name = self.LANGUAGE_NAMES.get(language, 'English')
            
            # Build messages
            messages = [{"role": "system", "content": self.SYSTEM_PROMPT}]
            
            # Add conversation history if available
            if conversation_history:
                for turn in conversation_history[-3:]:  # Last 3 turns
                    messages.append({"role": "user", "content": turn.get('user', '')})
                    messages.append({"role": "assistant", "content": turn.get('bot', '')})
            
            # Build user message with context
            user_message = f"User question: {user_input}"
            
            # Add language instruction based on target language
            lang_instruction = {
                'hi': "आपको हिंदी में जवाब देना है। (You MUST respond in Hindi only)",
                'te': "మీరు తెలుగులో సమాధానం ఇవ్వాలి. (You MUST respond in Telugu only)",
                'en': "You MUST respond in English only."
            }.get(language, "You MUST respond in English only.")
            
            if db_context:
                user_message = f"""Database Information:
{db_context}

{user_message}

LANGUAGE: {lang_name}
{lang_instruction}
Give a direct, concise answer (1-2 sentences)."""
            else:
                user_message = f"""{user_message}

LANGUAGE: {lang_name}
{lang_instruction}
Be concise and helpful."""
            
            messages.append({"role": "user", "content": user_message})
            
            # Call OpenAI API
            logger.info(f"Calling OpenAI GPT-4o-mini for: {user_input[:50]}...")
            
            response = await self.async_client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=300
            )
            
            result = response.choices[0].message.content.strip()
            
            # Log the generated response clearly
            logger.info("=" * 50)
            logger.info(f"[GPT-4o-mini RESPONSE] Language: {lang_name}")
            logger.info(f"[GPT-4o-mini RESPONSE] Text: {result}")
            logger.info("=" * 50)
            
            return result
            
        except Exception as e:
            logger.error(f"OpenAI generation failed: {e}")
            return self._get_fallback_response(language)
    
    async def text_to_speech(self, text: str, language: str = 'en') -> Optional[str]:
        """Convert text to speech using gTTS"""
        if not GTTS_AVAILABLE:
            logger.warning("gTTS not available for TTS")
            return None
        
        try:
            lang_code = {'en': 'en', 'hi': 'hi', 'te': 'te'}.get(language, 'en')
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            filename = f"response_{timestamp}_{language}.mp3"
            filepath = os.path.join(self._audio_dir, filename)
            
            # Generate audio in background thread
            def generate_audio():
                tts = gTTS(text=text, lang=lang_code, slow=False)
                tts.save(filepath)
                return filepath
            
            result = await asyncio.to_thread(generate_audio)
            logger.info(f"Audio generated: {result}")
            return result
            
        except Exception as e:
            logger.error(f"TTS failed: {e}")
            return None
    
    def _get_fallback_response(self, language: str) -> str:
        """Get fallback response in appropriate language"""
        fallbacks = {
            'en': "I'm sorry, I couldn't process your request. Please contact the hospital reception for assistance.",
            'hi': "क्षमा करें, मैं आपके अनुरोध को संसाधित नहीं कर सका। कृपया सहायता के लिए अस्पताल के रिसेप्शन से संपर्क करें।",
            'te': "క్షమించండి, మీ అభ్యర్థనను ప్రాసెస్ చేయలేకపోయాను. దయచేసి సహాయం కోసం ఆసుపత్రి రిసెప్షన్‌ను సంప్రదించండి."
        }
        return fallbacks.get(language, fallbacks['en'])
    
    async def health_check(self) -> Dict[str, Any]:
        """Check service health"""
        return {
            'initialized': self._initialized,
            'model': self.model,
            'openai_available': OPENAI_AVAILABLE,
            'gtts_available': GTTS_AVAILABLE
        }


# Global instance
_openai_service: Optional[OpenAIService] = None


async def get_openai_service() -> OpenAIService:
    """Get or create OpenAI service instance"""
    global _openai_service
    if _openai_service is None:
        _openai_service = OpenAIService()
        await _openai_service.initialize()
    return _openai_service
