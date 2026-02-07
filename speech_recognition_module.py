"""Speech recognition module for capturing and processing audio input."""

try:
    import speech_recognition as sr
    SPEECH_RECOGNITION_AVAILABLE = True
except ImportError:
    SPEECH_RECOGNITION_AVAILABLE = False
    print("Warning: speech_recognition module not available. Voice input will not work.")

from config import (
    SPEECH_RECOGNITION_TIMEOUT,
    SPEECH_RECOGNITION_PHRASE_LIMIT,
    ENERGY_THRESHOLD
)


class SpeechRecognizer:
    """Handles speech recognition from microphone input."""
    
    def __init__(self):
        """Initialize the speech recognizer."""
        if not SPEECH_RECOGNITION_AVAILABLE:
            self.recognizer = None
            self.microphone = None
            return
        
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = ENERGY_THRESHOLD
        self.microphone = None
        
    def initialize_microphone(self):
        """Initialize the microphone."""
        if not SPEECH_RECOGNITION_AVAILABLE:
            print("Speech recognition not available.")
            return False
        
        try:
            self.microphone = sr.Microphone()
            return True
        except Exception as e:
            print(f"Error initializing microphone: {e}")
            return False
    
    def listen(self):
        """
        Listen to audio input from microphone and convert to text.
        
        Returns:
            str: Recognized text or None if recognition failed
        """
        if not SPEECH_RECOGNITION_AVAILABLE:
            print("Speech recognition not available.")
            return None
        
        if not self.microphone:
            if not self.initialize_microphone():
                return None
        
        try:
            with self.microphone as source:
                print("Listening...")
                # Adjust for ambient noise
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                # Listen for audio
                audio = self.recognizer.listen(
                    source,
                    timeout=SPEECH_RECOGNITION_TIMEOUT,
                    phrase_time_limit=SPEECH_RECOGNITION_PHRASE_LIMIT
                )
                
            # Recognize speech using Google Speech Recognition
            print("Processing speech...")
            text = self.recognizer.recognize_google(audio)
            return text
            
        except Exception as e:
            if SPEECH_RECOGNITION_AVAILABLE:
                error_type = type(e).__name__
                if 'WaitTimeoutError' in error_type:
                    print("Listening timed out. No speech detected.")
                elif 'UnknownValueError' in error_type:
                    print("Could not understand audio")
                elif 'RequestError' in error_type:
                    print(f"Could not request results from speech recognition service; {e}")
                else:
                    print(f"Error during speech recognition: {e}")
            else:
                print(f"Error: {e}")
            return None
    
    def listen_from_file(self, audio_file_path):
        """
        Process audio from a file (useful for testing).
        
        Args:
            audio_file_path: Path to the audio file
            
        Returns:
            str: Recognized text or None if recognition failed
        """
        if not SPEECH_RECOGNITION_AVAILABLE:
            print("Speech recognition not available.")
            return None
        
        try:
            with sr.AudioFile(audio_file_path) as source:
                audio = self.recognizer.record(source)
                text = self.recognizer.recognize_google(audio)
                return text
        except Exception as e:
            print(f"Error processing audio file: {e}")
            return None
