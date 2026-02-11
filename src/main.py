"""
Clinic Assistant Chatbot - Main Application
FastAPI with WebSocket support for real-time voice/text interactions
Enterprise-grade deployment with health checks and monitoring
"""
import logging
import sys
import os
import asyncio
from contextlib import asynccontextmanager
from typing import Optional
from datetime import datetime

# Ensure UTF-8 encoding on Windows
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

# FastAPI imports
try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, UploadFile, File, Form
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
    from pydantic import BaseModel
    import uvicorn
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    print("FastAPI not installed. Run: pip install fastapi uvicorn")

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Project root directory (parent of src)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(PROJECT_ROOT, 'logs')
AUDIO_DIR = os.path.join(LOGS_DIR, 'audio')

from config import get_config
from orchestration.pipecat_orchestrator import get_orchestrator, PipecatOrchestrator

# Ensure logs directory exists
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)

# Simple logging to console only (avoid file lock issues)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


# ========================================
# PYDANTIC MODELS
# ========================================

class ChatRequest(BaseModel):
    """Request model for chat endpoint"""
    message: str
    session_id: Optional[str] = None
    language: Optional[str] = None


class ChatResponse(BaseModel):
    """Response model for chat endpoint"""
    success: bool
    response: str
    audio_url: Optional[str] = None
    language: str
    session_id: str
    intent: Optional[str] = None
    confidence: float = 0.0
    processing_time_ms: int = 0


class SessionRequest(BaseModel):
    """Request model for session creation"""
    speaker_name: Optional[str] = None
    language: Optional[str] = None


class HealthResponse(BaseModel):
    """Response model for health check"""
    status: str
    timestamp: str
    components: dict


# ========================================
# APPLICATION LIFECYCLE
# ========================================

orchestrator: Optional[PipecatOrchestrator] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management"""
    global orchestrator
    
    logger.info("Starting Clinic Assistant Chatbot...")
    
    # Initialize orchestrator
    orchestrator = await get_orchestrator()
    logger.info("Orchestrator initialized")
    
    yield
    
    # Cleanup
    logger.info("Shutting down...")
    if orchestrator and orchestrator.db:
        await orchestrator.db.close()


# ========================================
# FASTAPI APPLICATION
# ========================================

if FASTAPI_AVAILABLE:
    config = get_config()
    
    app = FastAPI(
        title="Clinic Assistant Chatbot",
        description="Enterprise-grade medical voice chatbot for NIMS Hospital",
        version="1.0.0",
        lifespan=lifespan
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.security.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # ========================================
    # REST ENDPOINTS
    # ========================================
    
    @app.get("/")
    async def root():
        """Root endpoint"""
        return {
            "service": "Clinic Assistant Chatbot",
            "status": "running",
            "version": "1.0.0",
            "hospital": "NIMS Hospital, Hyderabad",
            "endpoints": {
                "voice_demo": "/voice",
                "realtime_voice": "/realtime",
                "api_chat": "/api/chat",
                "api_health": "/health"
            }
        }
    
    @app.get("/voice", response_class=HTMLResponse)
    async def voice_demo():
        """Serve the voice assistant demo page"""
        demo_path = os.path.join(PROJECT_ROOT, 'static', 'voice_demo.html')
        if os.path.exists(demo_path):
            with open(demo_path, 'r', encoding='utf-8') as f:
                return HTMLResponse(content=f.read())
        return HTMLResponse(content="<h1>Voice demo not found</h1>", status_code=404)
    
    @app.get("/realtime", response_class=HTMLResponse)
    async def realtime_voice():
        """Serve the real-time transcription voice UI"""
        demo_path = os.path.join(PROJECT_ROOT, 'static', 'realtime_voice.html')
        if os.path.exists(demo_path):
            with open(demo_path, 'r', encoding='utf-8') as f:
                return HTMLResponse(content=f.read())
        return HTMLResponse(content="<h1>Real-time voice UI not found</h1>", status_code=404)
    
    @app.get("/health", response_model=HealthResponse)
    async def health_check():
        """Health check endpoint for monitoring"""
        global orchestrator
        
        if orchestrator:
            health = await orchestrator.health_check()
            status = "healthy" if health.get('orchestrator') == 'healthy' else "degraded"
        else:
            health = {"orchestrator": "not_initialized"}
            status = "unhealthy"
        
        return HealthResponse(
            status=status,
            timestamp=datetime.utcnow().isoformat(),
            components=health
        )
    
    @app.post("/api/session")
    async def create_session(request: SessionRequest):
        """Create a new conversation session"""
        global orchestrator
        
        if not orchestrator:
            raise HTTPException(status_code=503, detail="Service not ready")
        
        context = orchestrator.create_session(
            speaker_name=request.speaker_name,
            language=request.language
        )
        
        return {
            "session_id": context.session_id,
            "speaker_name": context.speaker_name,
            "language": context.language
        }
    
    @app.post("/api/chat", response_model=ChatResponse)
    async def chat(request: ChatRequest):
        """
        Main chat endpoint for text interactions
        Supports: English, Hindi, Telugu
        """
        global orchestrator
        
        if not orchestrator:
            raise HTTPException(status_code=503, detail="Service not ready")
        
        if not request.message or not request.message.strip():
            raise HTTPException(status_code=400, detail="Message cannot be empty")
        
        # Process the message - pass language from request if specified
        result = await orchestrator.process_input(
            user_input=request.message.strip(),
            session_id=request.session_id,
            detected_language=request.language  # Use the language from request
        )
        
        # Get session ID
        session_id = request.session_id
        if not session_id:
            # Find the most recent session
            if orchestrator.sessions:
                session_id = list(orchestrator.sessions.keys())[-1]
            else:
                session_id = "unknown"
        
        # Generate audio URL if audio was created
        audio_url = None
        if result.response_audio_path:
            audio_url = f"/api/audio/{os.path.basename(result.response_audio_path)}"
        
        return ChatResponse(
            success=result.success,
            response=result.response_text,
            audio_url=audio_url,
            language=result.language,
            session_id=session_id,
            intent=result.intent.value if hasattr(result.intent, 'value') else str(result.intent) if result.intent else None,
            confidence=result.confidence,
            processing_time_ms=result.processing_time_ms
        )
    
    @app.get("/api/audio/{filename}")
    async def get_audio(filename: str):
        """Serve audio files"""
        audio_path = os.path.join(AUDIO_DIR, filename)
        
        if not os.path.exists(audio_path):
            raise HTTPException(status_code=404, detail="Audio file not found")
        
        return FileResponse(
            audio_path,
            media_type="audio/mpeg",
            filename=filename
        )
    
    @app.post("/api/voice")
    async def process_voice(
        audio: UploadFile = File(...),
        session_id: Optional[str] = Form(None),
        language: Optional[str] = Form(None)
    ):
        """
        Voice chat endpoint - accepts audio file and returns response with audio
        
        Supports:
        - WAV, WEBM, OGG audio formats
        - Automatic language detection (English, Hindi, Telugu)
        - Returns text response and audio URL
        
        Pipeline: Listen → Understand → Respond → Speak
        """
        global orchestrator
        
        if not orchestrator:
            raise HTTPException(status_code=503, detail="Service not ready")
        
        # Read audio data
        audio_bytes = await audio.read()
        
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="No audio data received")
        
        logger.info(f"Voice input received: {len(audio_bytes)} bytes, type: {audio.content_type}")
        
        # Process voice through orchestrator
        result = await orchestrator.process_voice_input(
            audio_bytes=audio_bytes,
            session_id=session_id,
            language_hint=language
        )
        
        # Get session ID
        if not session_id:
            if orchestrator.sessions:
                session_id = list(orchestrator.sessions.keys())[-1]
            else:
                session_id = "unknown"
        
        # Generate audio URL if audio was created
        audio_url = None
        if result.response_audio_path:
            audio_url = f"/api/audio/{os.path.basename(result.response_audio_path)}"
        
        return {
            "success": result.success,
            "transcription": result.response_text if not result.success else None,
            "response": result.response_text,
            "audio_url": audio_url,
            "language": result.language,
            "session_id": session_id,
            "intent": result.intent.value if hasattr(result.intent, 'value') else str(result.intent) if result.intent else None,
            "confidence": result.confidence,
            "processing_time_ms": result.processing_time_ms
        }
    
    @app.delete("/api/session/{session_id}")
    async def end_session(session_id: str):
        """End a conversation session"""
        global orchestrator
        
        if not orchestrator:
            raise HTTPException(status_code=503, detail="Service not ready")
        
        orchestrator.end_session(session_id)
        
        return {"message": "Session ended", "session_id": session_id}
    
    # ========================================
    # WEBSOCKET FOR REAL-TIME VOICE
    # ========================================
    
    @app.websocket("/ws/voice")
    async def websocket_voice(websocket: WebSocket):
        """
        WebSocket endpoint for real-time voice interactions
        
        Protocol:
        1. Connect → receive session info
        2. Send audio (binary) → receive transcription + response + audio URL
        3. Send text → receive response + audio URL
        
        Message Types (from server):
        - connected: Connection established
        - listening: Server is ready for audio
        - transcription: STT result
        - response: AI response with audio
        - error: Error occurred
        """
        global orchestrator
        
        await websocket.accept()
        logger.info("Voice WebSocket connection established")
        
        # Create session for this connection
        session_context = orchestrator.create_session() if orchestrator else None
        session_id = session_context.session_id if session_context else "unknown"
        
        # Audio buffer for accumulating chunks
        audio_buffer = bytearray()
        
        try:
            # Send welcome message
            await websocket.send_json({
                "type": "connected",
                "session_id": session_id,
                "message": "Connected to NIMS Hospital Voice Assistant",
                "supported_languages": ["en", "hi", "te"],
                "instructions": "Send audio as binary data or text for processing"
            })
            
            while True:
                # Receive message (text or binary audio)
                try:
                    data = await asyncio.wait_for(
                        websocket.receive(),
                        timeout=300  # 5 minute timeout
                    )
                except asyncio.TimeoutError:
                    logger.info("WebSocket timeout")
                    break
                
                if "text" in data:
                    # Text message (could be JSON command or plain text)
                    message = data["text"]
                    
                    try:
                        import json
                        json_data = json.loads(message)
                        
                        if json_data.get("type") == "end_audio":
                            # Process accumulated audio
                            if audio_buffer and orchestrator:
                                await websocket.send_json({"type": "processing"})
                                
                                result = await orchestrator.process_voice_input(
                                    audio_bytes=bytes(audio_buffer),
                                    session_id=session_id
                                )
                                
                                await websocket.send_json({
                                    "type": "response",
                                    "transcription": result.response_text if result.source == 'stt_failed' else None,
                                    "text": result.response_text,
                                    "language": result.language,
                                    "intent": result.intent.value if result.intent else None,
                                    "confidence": result.confidence,
                                    "audio_url": f"/api/audio/{os.path.basename(result.response_audio_path)}" if result.response_audio_path else None,
                                    "processing_time_ms": result.processing_time_ms
                                })
                                
                                audio_buffer = bytearray()
                            continue
                        
                        elif json_data.get("type") == "text":
                            # Process text input
                            text_message = json_data.get("message", "")
                    except json.JSONDecodeError:
                        # Plain text message
                        text_message = message
                    
                    logger.info(f"WS received text: {message}")
                    
                    if orchestrator:
                        result = await orchestrator.process_input(
                            user_input=message,
                            session_id=session_id
                        )
                        
                        await websocket.send_json({
                            "type": "response",
                            "text": result.response_text,
                            "language": result.language,
                            "intent": result.intent.value if result.intent else None,
                            "confidence": result.confidence,
                            "audio_url": f"/api/audio/{os.path.basename(result.response_audio_path)}" if result.response_audio_path else None,
                            "processing_time_ms": result.processing_time_ms
                        })
                    else:
                        await websocket.send_json({
                            "type": "error",
                            "text": "Service not ready"
                        })
                
                elif "bytes" in data:
                    # Binary audio data
                    audio_data = data["bytes"]
                    audio_buffer.extend(audio_data)
                    logger.debug(f"WS received audio chunk: {len(audio_data)} bytes, total: {len(audio_buffer)}")
                    
                    # Check if we have enough audio for processing (at least 1 second at 16kHz mono 16-bit)
                    MIN_AUDIO_BYTES = 32000  # ~1 second
                    
                    if len(audio_buffer) >= MIN_AUDIO_BYTES:
                        # Auto-process if we have enough audio and there's a pause
                        await websocket.send_json({
                            "type": "audio_received",
                            "size": len(audio_buffer),
                            "duration_ms": int(len(audio_buffer) / 32)  # Approximate
                        })
        
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected: {session_id}")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            if orchestrator and session_id:
                orchestrator.end_session(session_id)
    
    @app.websocket("/ws/text")
    async def websocket_text(websocket: WebSocket):
        """
        WebSocket endpoint for real-time text chat
        Simpler alternative to voice WebSocket
        """
        global orchestrator
        
        await websocket.accept()
        logger.info("Text WebSocket connection established")
        
        session_context = orchestrator.create_session() if orchestrator else None
        session_id = session_context.session_id if session_context else "unknown"
        
        try:
            await websocket.send_json({
                "type": "connected",
                "session_id": session_id
            })
            
            while True:
                message = await websocket.receive_text()
                
                if orchestrator:
                    result = await orchestrator.process_input(
                        user_input=message,
                        session_id=session_id
                    )
                    
                    await websocket.send_json({
                        "type": "response",
                        "text": result.response_text,
                        "language": result.language,
                        "processing_time_ms": result.processing_time_ms
                    })
                else:
                    await websocket.send_json({
                        "type": "error",
                        "text": "Service not ready"
                    })
        
        except WebSocketDisconnect:
            logger.info(f"Text WebSocket disconnected: {session_id}")
        except Exception as e:
            logger.error(f"Text WebSocket error: {e}")
        finally:
            if orchestrator:
                orchestrator.end_session(session_id)


# ========================================
# MAIN ENTRY POINT
# ========================================

def main():
    """Main entry point"""
    if not FASTAPI_AVAILABLE:
        print("FastAPI not available. Install with: pip install fastapi uvicorn")
        return
    
    
    
    uvicorn.run(
        "main:app",
        host=config.server.host,
        port=config.server.port,
        reload=config.server.debug,
        workers=1 if config.server.debug else config.server.workers,
        log_level=config.server.log_level.lower()
    )


if __name__ == "__main__":
    main()
