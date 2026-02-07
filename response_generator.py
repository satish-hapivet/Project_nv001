"""Response generator for creating appropriate responses to user queries."""

from hospital_data import (
    get_doctors_info,
    get_department_info,
    get_service_info,
    get_emergency_info,
    HOSPITAL_DATA
)
from config import UNKNOWN_QUERY_MESSAGE


class ResponseGenerator:
    """Generates appropriate responses based on user intent and query."""
    
    def __init__(self):
        """Initialize the response generator."""
        pass
    
    def generate_response(self, intent, entities, original_text):
        """
        Generate response based on intent and entities.
        
        Args:
            intent: Detected user intent
            entities: Extracted entities from query
            original_text: Original user query
            
        Returns:
            str: Generated response
        """
        if intent == 'doctor':
            return self._generate_doctor_response(entities, original_text)
        elif intent == 'department':
            return self._generate_department_response(entities, original_text)
        elif intent == 'service':
            return self._generate_service_response(entities, original_text)
        elif intent == 'emergency':
            return self._generate_emergency_response(entities, original_text)
        elif intent == 'appointment':
            return self._generate_appointment_response()
        elif intent == 'hours':
            return self._generate_hours_response(entities, original_text)
        elif intent == 'location':
            return self._generate_location_response(entities, original_text)
        else:
            return UNKNOWN_QUERY_MESSAGE
    
    def _generate_doctor_response(self, entities, text):
        """Generate response for doctor-related queries."""
        # Check for specific specialization in the original text
        specialization = None
        text_lower = text.lower()
        
        # Check common specialization terms in text (using singular forms that patients typically say)
        # The get_doctors_info function handles partial matching, so 'orthopedic' matches 'orthopedics'
        specializations_to_check = ['orthopedic', 'cardiology', 'neurology', 'pediatric', 'radiology']
        for spec in specializations_to_check:
            if spec in text_lower:
                specialization = spec
                break
        
        # Also check from entities
        if not specialization:
            for entity in entities:
                if entity['type'] == 'specialization':
                    specialization = entity['value']
                    break
        
        if specialization:
            doctors = get_doctors_info(specialization)
            if doctors:
                response = f"We have the following doctors in {specialization}:\n"
                for doc in doctors:
                    response += f"- {doc['name']}, {doc['specialization']}, available {doc['availability']}\n"
                return response.strip()
        
        # General doctor info
        return "We have specialists in Cardiology, Neurology, Pediatrics, and Orthopedics. Which department would you like to know about?"
    
    def _generate_department_response(self, entities, text):
        """Generate response for department-related queries."""
        # Check for specific department
        department = None
        for entity in entities:
            if entity['type'] == 'specialization':
                department = entity['value']
                break
        
        if department:
            dept_info = get_department_info(department)
            if dept_info:
                return (f"{dept_info['name']} is located at {dept_info['location']}. "
                       f"Hours: {dept_info['hours']}. Contact: {dept_info['contact']}.")
        
        # List all departments
        departments = HOSPITAL_DATA['departments']
        response = "We have the following departments:\n"
        for dept_data in departments.values():
            response += f"- {dept_data['name']}: {dept_data['location']}\n"
        return response.strip()
    
    def _generate_service_response(self, entities, text):
        """Generate response for service-related queries."""
        # Check for specific service
        service = None
        for entity in entities:
            if entity['type'] == 'service':
                service = entity['value']
                break
        
        if service:
            service_info = get_service_info(service)
            if service_info:
                return (f"{service_info['name']}: {service_info['description']}. "
                       f"Located at {service_info['location']}. Hours: {service_info['hours']}.")
        
        # List all services
        services = HOSPITAL_DATA['services']
        response = "We offer the following services:\n"
        for service_data in services.values():
            response += f"- {service_data['name']}: {service_data['description']}\n"
        return response.strip()
    
    def _generate_emergency_response(self, entities, text):
        """Generate response for emergency-related queries."""
        # Check for specific emergency type
        text_lower = text.lower()
        emergency_type = None
        
        if 'chest' in text_lower or 'heart' in text_lower:
            emergency_type = 'chest_pain'
        elif 'stroke' in text_lower:
            emergency_type = 'stroke'
        elif 'injury' in text_lower or 'accident' in text_lower:
            emergency_type = 'injury'
        elif 'ambulance' in text_lower:
            emergency_type = 'ambulance'
        
        return get_emergency_info(emergency_type)
    
    def _generate_appointment_response(self):
        """Generate response for appointment-related queries."""
        return ("To schedule an appointment, please call our appointment desk at Extension 200 "
               "or visit the reception desk on the ground floor. You can also book online through "
               "our hospital portal.")
    
    def _generate_hours_response(self, entities, text):
        """Generate response for hours/timing queries."""
        # Check for specific department or service
        for entity in entities:
            if entity['type'] == 'specialization':
                dept_info = get_department_info(entity['value'])
                if dept_info:
                    return f"{dept_info['name']} hours: {dept_info['hours']}"
            elif entity['type'] == 'service':
                service_info = get_service_info(entity['value'])
                if service_info:
                    return f"{service_info['name']} hours: {service_info['hours']}"
        
        return "Our Emergency Department is open 24/7. Most other departments are open Monday to Friday 8AM-6PM. Would you like information about a specific department?"
    
    def _generate_location_response(self, entities, text):
        """Generate response for location-related queries."""
        # Check for specific department or service
        for entity in entities:
            if entity['type'] == 'specialization':
                dept_info = get_department_info(entity['value'])
                if dept_info:
                    return f"{dept_info['name']} is located at {dept_info['location']}."
            elif entity['type'] == 'service':
                service_info = get_service_info(entity['value'])
                if service_info:
                    return f"{service_info['name']} is located at {service_info['location']}."
        
        return "The main entrance is at the front of the building. Emergency Department is at Ground Floor, Wing A. For specific locations, please ask about a particular department or service."
