"""
Configuration Management for NIMS Hospital Voice Assistant
Clean Architecture - Infrastructure Layer
"""
import os
import sys
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


@dataclass
class OpenAIConfig:
    """OpenAI API Configuration"""
    api_key: str = field(default_factory=lambda: os.getenv('OPENAI_API_KEY', ''))
    model: str = field(default_factory=lambda: os.getenv('OPENAI_MODEL', 'gpt-4o-mini'))
    max_tokens: int = field(default_factory=lambda: int(os.getenv('OPENAI_MAX_TOKENS', '500')))
    temperature: float = field(default_factory=lambda: float(os.getenv('OPENAI_TEMPERATURE', '0.7')))
    
    def validate(self) -> bool:
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required")
        return True


@dataclass
class PostgresConfig:
    """PostgreSQL Database Configuration"""
    host: str = field(default_factory=lambda: os.getenv('POSTGRES_HOST', 'localhost'))
    port: int = field(default_factory=lambda: int(os.getenv('POSTGRES_PORT', '5432')))
    database: str = field(default_factory=lambda: os.getenv('POSTGRES_DATABASE', 'nims_hospital_db'))
    user: str = field(default_factory=lambda: os.getenv('POSTGRES_USER', 'postgres'))
    password: str = field(default_factory=lambda: os.getenv('POSTGRES_PASSWORD', ''))
    ssl_mode: str = field(default_factory=lambda: os.getenv('POSTGRES_SSL_MODE', 'prefer'))
    min_connections: int = 5
    max_connections: int = 20
    
    @property
    def connection_string(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}?sslmode={self.ssl_mode}"
    
    def validate(self) -> bool:
        if not self.password:
            raise ValueError("POSTGRES_PASSWORD is required")
        return True


@dataclass
class RedisConfig:
    """Redis Cache Configuration (Optional)"""
    host: str = field(default_factory=lambda: os.getenv('REDIS_HOST', 'localhost'))
    port: int = field(default_factory=lambda: int(os.getenv('REDIS_PORT', '6379')))
    password: Optional[str] = field(default_factory=lambda: os.getenv('REDIS_PASSWORD', None))
    db: int = field(default_factory=lambda: int(os.getenv('REDIS_DB', '0')))
    ttl: int = 3600
    
    @property
    def connection_url(self) -> str:
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"


@dataclass
class ServerConfig:
    """Server Configuration"""
    host: str = field(default_factory=lambda: os.getenv('SERVER_HOST', '0.0.0.0'))
    port: int = field(default_factory=lambda: int(os.getenv('SERVER_PORT', '8001')))
    debug: bool = field(default_factory=lambda: os.getenv('DEBUG_MODE', 'false').lower() == 'true')
    log_level: str = field(default_factory=lambda: os.getenv('LOG_LEVEL', 'INFO'))
    allowed_origins: list = field(default_factory=lambda: os.getenv('ALLOWED_ORIGINS', '*').split(','))


@dataclass
class LanguageConfig:
    """Language Configuration"""
    default_language: str = field(default_factory=lambda: os.getenv('DEFAULT_LANGUAGE', 'en'))
    supported_languages: list = field(default_factory=lambda: ['en', 'hi', 'te'])
    speaker_name: str = field(default_factory=lambda: os.getenv('SPEAKER_NAME', 'NIMS Assistant'))
    
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


@dataclass
class STTConfig:
    """Speech-to-Text Configuration (faster-whisper)"""
    model_size: str = field(default_factory=lambda: os.getenv('WHISPER_MODEL', 'medium'))
    device: str = field(default_factory=lambda: os.getenv('WHISPER_DEVICE', 'cpu'))
    compute_type: str = 'int8'
    beam_size: int = 5
    sample_rate: int = 16000


@dataclass
class TTSConfig:
    """Text-to-Speech Configuration (edge-tts)"""
    voice_en: str = field(default_factory=lambda: os.getenv('TTS_VOICE_EN', 'en-IN-NeerjaNeural'))
    voice_hi: str = field(default_factory=lambda: os.getenv('TTS_VOICE_HI', 'hi-IN-NeerjaNeural'))
    voice_te: str = field(default_factory=lambda: os.getenv('TTS_VOICE_TE', 'te-IN-ShrutiNeural'))


@dataclass
class AppConfig:
    """Main Application Configuration"""
    openai: OpenAIConfig = field(default_factory=OpenAIConfig)
    postgres: PostgresConfig = field(default_factory=PostgresConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    language: LanguageConfig = field(default_factory=LanguageConfig)
    stt: STTConfig = field(default_factory=STTConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    
    def validate_all(self, strict: bool = False) -> bool:
        """Validate all configurations"""
        errors = []
        
        try:
            self.openai.validate()
        except ValueError as e:
            errors.append(str(e))
        
        if strict:
            try:
                self.postgres.validate()
            except ValueError as e:
                errors.append(str(e))
        
        if errors:
            for error in errors:
                print(f"Configuration Error: {error}", file=sys.stderr)
            return False
        
        return True


# Global configuration instance
config = AppConfig()


def get_config() -> AppConfig:
    """Get the global configuration instance"""
    return config


if __name__ == "__main__":
    cfg = get_config()
    print(f"OpenAI API Key: {'*' * 10 + cfg.openai.api_key[-4:] if cfg.openai.api_key else 'Not set'}")
    print(f"PostgreSQL Host: {cfg.postgres.host}")
    print(f"Server Port: {cfg.server.port}")
    print(f"Default Language: {cfg.language.default_language}")
