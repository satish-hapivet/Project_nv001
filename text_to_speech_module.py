"""Text-to-speech module for converting text responses to audio output."""

try:
    import pyttsx3
    PYTTSX3_AVAILABLE = True
except ImportError:
    PYTTSX3_AVAILABLE = False
    print("Warning: pyttsx3 module not available. Voice output will not work.")

from config import TTS_RATE, TTS_VOLUME


class TextToSpeech:
    """Handles text-to-speech conversion."""
    
    def __init__(self):
        """Initialize the text-to-speech engine."""
        if not PYTTSX3_AVAILABLE:
            self.engine = None
            self.enabled = False
            return
        
        try:
            self.engine = pyttsx3.init()
            self.engine.setProperty('rate', TTS_RATE)
            self.engine.setProperty('volume', TTS_VOLUME)
            self.enabled = True
        except Exception as e:
            print(f"Warning: Could not initialize text-to-speech engine: {e}")
            self.engine = None
            self.enabled = False
    
    def speak(self, text):
        """
        Convert text to speech and play it.
        
        Args:
            text: The text to convert to speech
        """
        if not self.enabled or not self.engine:
            print(f"[TTS Disabled] Would say: {text}")
            return
        
        try:
            print(f"Assistant: {text}")
            self.engine.say(text)
            self.engine.runAndWait()
        except Exception as e:
            print(f"Error during text-to-speech: {e}")
            print(f"Message was: {text}")
    
    def set_rate(self, rate):
        """
        Set the speaking rate.
        
        Args:
            rate: Words per minute (typically 150-200)
        """
        if self.enabled and self.engine:
            self.engine.setProperty('rate', rate)
    
    def set_volume(self, volume):
        """
        Set the volume level.
        
        Args:
            volume: Volume level (0.0 to 1.0)
        """
        if self.enabled and self.engine:
            self.engine.setProperty('volume', volume)
    
    def get_available_voices(self):
        """
        Get list of available voices.
        
        Returns:
            list: Available voice objects
        """
        if self.enabled and self.engine:
            return self.engine.getProperty('voices')
        return []
    
    def set_voice(self, voice_id):
        """
        Set the voice to use.
        
        Args:
            voice_id: ID of the voice to use
        """
        if self.enabled and self.engine:
            self.engine.setProperty('voice', voice_id)
