"""Main Hospital Assistant Robot controller integrating all modules."""

from speech_recognition_module import SpeechRecognizer
from text_to_speech_module import TextToSpeech
from nlp_module import NLPProcessor
from response_generator import ResponseGenerator
from config import GREETING_MESSAGE, GOODBYE_MESSAGE


class HospitalAssistant:
    """Main hospital assistant robot controller."""
    
    def __init__(self, use_voice=True):
        """
        Initialize the hospital assistant.
        
        Args:
            use_voice: Whether to use voice input/output (False for text-only mode)
        """
        self.use_voice = use_voice
        self.speech_recognizer = SpeechRecognizer() if use_voice else None
        self.tts = TextToSpeech()
        self.nlp_processor = NLPProcessor()
        self.response_generator = ResponseGenerator()
        self.is_running = False
    
    def start(self):
        """Start the hospital assistant."""
        self.is_running = True
        self._speak(GREETING_MESSAGE)
        
        if self.use_voice:
            self._run_voice_mode()
        else:
            self._run_text_mode()
    
    def stop(self):
        """Stop the hospital assistant."""
        self.is_running = False
        self._speak(GOODBYE_MESSAGE)
    
    def _run_voice_mode(self):
        """Run the assistant in voice mode."""
        print("\n=== Voice Mode Active ===")
        print("Speak your questions. Say 'exit' or 'goodbye' to quit.\n")
        
        while self.is_running:
            try:
                # Listen for user input
                user_input = self.speech_recognizer.listen()
                
                if user_input:
                    print(f"You said: {user_input}")
                    self._process_query(user_input)
                else:
                    print("No input detected. Please try again.")
                    
            except KeyboardInterrupt:
                print("\n\nInterrupted by user.")
                break
            except Exception as e:
                print(f"Error: {e}")
                continue
        
        self.stop()
    
    def _run_text_mode(self):
        """Run the assistant in text mode (for testing/demo)."""
        print("\n=== Text Mode Active ===")
        print("Type your questions. Type 'exit' or 'quit' to quit.\n")
        
        while self.is_running:
            try:
                # Get text input
                user_input = input("You: ").strip()
                
                if user_input:
                    self._process_query(user_input)
                    
            except KeyboardInterrupt:
                print("\n\nInterrupted by user.")
                break
            except EOFError:
                break
            except Exception as e:
                print(f"Error: {e}")
                continue
        
        self.stop()
    
    def _process_query(self, query):
        """
        Process a user query and generate response.
        
        Args:
            query: User query text
        """
        # Check if user wants to exit
        if self.nlp_processor.should_exit(query):
            self.is_running = False
            return
        
        # Process query with NLP
        analysis = self.nlp_processor.process_query(query)
        
        # Generate response
        response = self.response_generator.generate_response(
            analysis['intent'],
            analysis['entities'],
            analysis['original_text']
        )
        
        # Speak/display response
        self._speak(response)
    
    def _speak(self, text):
        """
        Output text via TTS or print.
        
        Args:
            text: Text to output
        """
        self.tts.speak(text)
    
    def process_single_query(self, query):
        """
        Process a single query without entering interactive mode.
        Useful for testing.
        
        Args:
            query: User query text
            
        Returns:
            str: Generated response
        """
        analysis = self.nlp_processor.process_query(query)
        response = self.response_generator.generate_response(
            analysis['intent'],
            analysis['entities'],
            analysis['original_text']
        )
        return response
