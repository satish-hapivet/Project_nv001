"""Configuration settings for the Hospital Assistant Robot."""

# Speech Recognition Settings
SPEECH_RECOGNITION_TIMEOUT = 5  # seconds
SPEECH_RECOGNITION_PHRASE_LIMIT = 10  # seconds
ENERGY_THRESHOLD = 4000  # Microphone sensitivity

# Text-to-Speech Settings
TTS_RATE = 150  # Words per minute
TTS_VOLUME = 0.9  # Volume level (0.0 to 1.0)

# Assistant Settings
ASSISTANT_NAME = "Hospital Assistant Robot"
GREETING_MESSAGE = "Hello! I am your hospital assistant. How may I help you today?"
GOODBYE_MESSAGE = "Thank you for using our service. Take care!"
UNKNOWN_QUERY_MESSAGE = "I'm sorry, I didn't understand that. Can you please rephrase your question?"

# Intent Keywords
INTENT_KEYWORDS = {
    'doctor': ['doctor', 'physician', 'specialist', 'surgeon'],
    'department': ['department', 'ward', 'unit', 'section'],
    'service': ['service', 'facility', 'treatment', 'procedure'],
    'emergency': ['emergency', 'urgent', 'critical', 'ambulance'],
    'appointment': ['appointment', 'schedule', 'booking'],
    'hours': ['hours', 'time', 'open', 'close', 'timing'],
    'location': ['where', 'location', 'find', 'direction']
}

# Exit Keywords
EXIT_KEYWORDS = ['exit', 'quit', 'bye', 'goodbye', 'stop', 'terminate']
