"""
NIMS Hospital Voice Assistant - Main Application
FastAPI with WebSocket support for real-time voice/text interactions
Production-grade deployment with health checks and monitoring
"""
import json
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
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, HTMLResponse
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
# APPLICATION SETUP (requires FastAPI)
# ========================================

if FASTAPI_AVAILABLE:

    # ── Pydantic Models ──────────────────────────────────────────

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
        language: Optional[str] = None

    class HealthResponse(BaseModel):
        """Response model for health check"""
        status: str
        timestamp: str
        components: dict

    # ── Application Lifecycle ────────────────────────────────────

    orchestrator: Optional[PipecatOrchestrator] = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Application lifecycle management"""
        global orchestrator

        logger.info("Starting NIMS Hospital Voice Assistant...")

        # Initialize orchestrator
        orchestrator = await get_orchestrator()
        logger.info("Orchestrator initialized")

        yield

        # Cleanup
        logger.info("Shutting down...")
        if orchestrator and orchestrator.db:
            await orchestrator.db.close()

    # ── FastAPI Application ──────────────────────────────────────
    config = get_config()
    
    app = FastAPI(
        title="NIMS Hospital Voice Assistant",
        description="Production-grade voice assistant for NIMS Multi-Speciality Hospital, Hyderabad",
        version="1.0.0",
        lifespan=lifespan
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.server.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ========================================
    # REST ENDPOINTS
    # ========================================
    
    @app.get("/", response_class=HTMLResponse)
    async def root():
        """Serve the real-time voice UI at root"""
        demo_path = os.path.join(PROJECT_ROOT, 'static', 'realtime_voice.html')
        if os.path.exists(demo_path):
            with open(demo_path, 'r', encoding='utf-8') as f:
                return HTMLResponse(content=f.read())
        return HTMLResponse(content="<h1>Real-time voice UI not found</h1>", status_code=404)
    
    @app.get("/realtime", response_class=HTMLResponse)
    async def realtime_voice():
        """Serve the real-time transcription voice UI (alias)"""
        return await root()
    
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
            language=request.language
        )
        
        return {
            "session_id": context.session_id,
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
            intent=str(result.intent) if result.intent else None,
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
        WebSocket endpoint for real-time voice/text interactions.

        Protocol:
        1. Connect → receive session info
        2. Send text (JSON or plain) → receive AI response + audio URL
        3. Send binary audio (PCM int16, 16 kHz mono) → STT → NLU → response + audio

        Message Types (from server):
        - connected: Connection established
        - response: AI response with optional audio
        - stt_result: Intermediate STT transcription (for UI display)
        - error: Error occurred
        """
        global orchestrator

        await websocket.accept()
        logger.info("Voice WebSocket connection established")

        session_context = orchestrator.create_session() if orchestrator else None
        session_id = session_context.session_id if session_context else "unknown"

        try:
            await websocket.send_json({
                "type": "connected",
                "session_id": session_id,
                "message": "Connected to NIMS Hospital Voice Assistant",
                "supported_languages": ["en", "hi", "te"],
                "stt_available": bool(orchestrator and orchestrator.stt),
            })

            while True:
                # Receive either text or binary
                message = await asyncio.wait_for(
                    websocket.receive(),
                    timeout=300,
                )

                if message.get("type") == "websocket.disconnect":
                    break

                # ── Binary audio frame ────────────────────────────
                if "bytes" in message and message["bytes"]:
                    audio_bytes = message["bytes"]
                    logger.info(f"WS received audio: {len(audio_bytes)} bytes")

                    if not orchestrator or not orchestrator.stt:
                        await websocket.send_json({
                            "type": "error",
                            "text": "Speech recognition not available",
                        })
                        continue

                    # Auto-detect language (no manual hint)
                    language_hint = None

                    # Step 1: STT transcription
                    stt_result = await orchestrator.stt.transcribe(
                        audio_bytes, language_hint=language_hint,
                    )

                    # Send STT result to UI for real-time display
                    await websocket.send_json({
                        "type": "stt_result",
                        "text": stt_result.text,
                        "language": stt_result.language,
                        "is_final": True,
                        "is_confident": stt_result.is_confident,
                    })

                    # Step 2: Full pipeline (STT already done, pass text)
                    result = await orchestrator.process_audio_input(
                        audio_bytes=audio_bytes,
                        session_id=session_id,
                        language_hint=language_hint,
                    )

                    response_payload = {
                        "type": "response",
                        "text": result.response_text,
                        "language": result.language,
                        "intent": str(result.intent) if result.intent else None,
                        "confidence": result.confidence,
                        "audio_url": f"/api/audio/{os.path.basename(result.response_audio_path)}" if result.response_audio_path else None,
                        "processing_time_ms": result.processing_time_ms,
                        "source": result.source,
                    }

                    # If TTS bytes available, also send audio binary frame
                    if result.response_audio_path and orchestrator.tts:
                        try:
                            with open(result.response_audio_path, "rb") as af:
                                audio_data = af.read()
                            await websocket.send_json(response_payload)
                            await websocket.send_bytes(audio_data)
                        except Exception:
                            await websocket.send_json(response_payload)
                    else:
                        await websocket.send_json(response_payload)

                    continue

                # ── Text frame ────────────────────────────────────
                text_data = message.get("text", "")
                if not text_data:
                    continue

                try:
                    json_data = json.loads(text_data)
                    text_input = json_data.get("message") or json_data.get("text") or text_data
                    # Auto-detect language; ignore manual hint
                    language_hint = None
                except (json.JSONDecodeError, TypeError):
                    text_input = text_data
                    language_hint = None

                if not text_input or not text_input.strip():
                    continue

                logger.info(f"WS received: {text_input[:80]}")

                if orchestrator:
                    result = await orchestrator.process_input(
                        user_input=text_input.strip(),
                        session_id=session_id,
                        detected_language=language_hint,
                    )
                    await websocket.send_json({
                        "type": "response",
                        "text": result.response_text,
                        "language": result.language,
                        "intent": str(result.intent) if result.intent else None,
                        "confidence": result.confidence,
                        "audio_url": f"/api/audio/{os.path.basename(result.response_audio_path)}" if result.response_audio_path else None,
                        "processing_time_ms": result.processing_time_ms,
                    })
                else:
                    await websocket.send_json({
                        "type": "error",
                        "text": "Service not ready",
                    })

        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected: {session_id}")
        except asyncio.TimeoutError:
            logger.info("WebSocket timeout")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            if orchestrator and session_id:
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
        workers=1,
        log_level=config.server.log_level.lower()
    )


if __name__ == "__main__":
    main()
