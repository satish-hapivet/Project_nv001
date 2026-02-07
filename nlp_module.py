"""Natural Language Processing module for understanding user queries."""

from config import INTENT_KEYWORDS


class NLPProcessor:
    """Handles natural language understanding and intent detection."""
    
    def __init__(self):
        """Initialize the NLP processor."""
        self.intent_keywords = INTENT_KEYWORDS
    
    def process_query(self, text):
        """
        Process user query and extract intent and entities.
        
        Args:
            text: User query text
            
        Returns:
            dict: Dictionary containing intent and extracted information
        """
        if not text:
            return {'intent': 'unknown', 'entities': []}
        
        text_lower = text.lower()
        
        # Detect intent
        intent = self._detect_intent(text_lower)
        
        # Extract entities (keywords that might be relevant)
        entities = self._extract_entities(text_lower)
        
        return {
            'intent': intent,
            'entities': entities,
            'original_text': text
        }
    
    def _detect_intent(self, text):
        """
        Detect the primary intent of the query.
        
        Args:
            text: Lowercase query text
            
        Returns:
            str: Detected intent
        """
        # Check for specific patterns first (higher priority)
        
        # Emergency indicators
        if any(word in text for word in ['emergency', 'urgent', 'chest pain', 'heart attack', 'stroke', 'ambulance', 'critical']):
            return 'emergency'
        
        # Information/need indicators combined with specific topics
        if 'information' in text or 'need' in text or 'tell' in text or 'about' in text:
            if any(word in text for word in ['pharmacy', 'lab', 'laboratory', 'cafeteria', 'imaging', 'service']):
                return 'service'
            if any(word in text for word in ['doctor', 'physician', 'specialist']):
                return 'doctor'
        
        # Count matches for each intent
        intent_scores = {}
        for intent, keywords in self.intent_keywords.items():
            score = sum(1 for keyword in keywords if keyword in text)
            if score > 0:
                intent_scores[intent] = score
        
        # Return intent with highest score
        if intent_scores:
            return max(intent_scores, key=intent_scores.get)
        
        return 'unknown'
    
    def _extract_entities(self, text):
        """
        Extract relevant entities from the text.
        
        Args:
            text: Lowercase query text
            
        Returns:
            list: List of extracted entities
        """
        entities = []
        words = text.split()
        
        # Common medical specializations
        specializations = [
            'cardiology', 'neurology', 'pediatrics', 'orthopedics',
            'radiology', 'emergency', 'surgery', 'medicine'
        ]
        
        # Common services
        services = [
            'laboratory', 'lab', 'pharmacy', 'imaging', 'xray', 'x-ray',
            'mri', 'ct scan', 'ultrasound', 'cafeteria'
        ]
        
        # Check for specializations
        for spec in specializations:
            if spec in text:
                entities.append({'type': 'specialization', 'value': spec})
        
        # Check for services
        for service in services:
            if service in text:
                entities.append({'type': 'service', 'value': service})
        
        return entities
    
    def should_exit(self, text):
        """
        Check if the user wants to exit the conversation.
        
        Args:
            text: User query text
            
        Returns:
            bool: True if user wants to exit
        """
        if not text:
            return False
        
        from config import EXIT_KEYWORDS
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in EXIT_KEYWORDS)
