# Hospital Assistant Robot - Usage Examples

This document provides examples of queries the Hospital Assistant Robot can understand and respond to.

## Emergency Queries

The assistant can handle various emergency situations:

- "I have a medical emergency"
- "I have chest pain"
- "Someone is having a stroke"
- "I need an ambulance"
- "Where is the emergency room?"
- "I've been in an accident"

**Example Response:**
```
Patient: I have chest pain
Assistant: If experiencing chest pain, call 911 immediately or go to Emergency Department. Do not drive yourself.
```

## Doctor Information

Ask about doctors in various specializations:

- "Who are the cardiologists?"
- "Tell me about cardiology doctors"
- "I need a neurologist"
- "Show me pediatric doctors"
- "Are there any orthopedic specialists?"
- "I need to see a doctor"

**Example Response:**
```
Patient: Tell me about cardiology doctors
Assistant: We have the following doctors in cardiology:
- Dr. Sarah Johnson, Cardiology, available Mon-Fri 9AM-5PM
- Dr. Michael Chen, Interventional Cardiology, available Tue-Sat 10AM-4PM
```

## Department Information

Get information about hospital departments:

- "Where is the cardiology department?"
- "Tell me about the neurology department"
- "I'm looking for pediatrics"
- "Where can I find radiology?"
- "Show me all departments"

**Example Response:**
```
Patient: Where is the cardiology department?
Assistant: Cardiology Department is located at 3rd Floor, Wing B. Hours: Mon-Fri 8AM-6PM, Sat 9AM-1PM. Contact: Extension 301.
```

## Services

Ask about various hospital services:

- "Where is the pharmacy?"
- "I need laboratory services"
- "Do you have imaging services?"
- "Where can I get an X-ray?"
- "Tell me about your cafeteria"
- "What services do you offer?"

**Example Response:**
```
Patient: I need information about the pharmacy
Assistant: Hospital Pharmacy: Prescription medications and medical supplies. Located at Ground Floor, Main Entrance. Hours: Mon-Sat 8AM-8PM, Sun 9AM-5PM.
```

## Hours and Timing

Check operating hours:

- "What are the hours for pediatrics?"
- "When is the pharmacy open?"
- "What time does radiology close?"
- "Are you open on weekends?"

**Example Response:**
```
Patient: What are the hours for pediatrics?
Assistant: Pediatrics Department hours: Mon-Fri 8AM-6PM, Sat 9AM-2PM
```

## Location and Directions

Find locations within the hospital:

- "Where can I find the cafeteria?"
- "How do I get to radiology?"
- "Where is the main entrance?"
- "Location of the emergency department"

**Example Response:**
```
Patient: Where can I find the cafeteria?
Assistant: Hospital Cafeteria is located at 1st Floor, Central Area.
```

## Appointments

Get information about scheduling appointments:

- "How do I schedule an appointment?"
- "I need to book an appointment"
- "Can I make an appointment?"

**Example Response:**
```
Patient: How do I schedule an appointment?
Assistant: To schedule an appointment, please call our appointment desk at Extension 200 or visit the reception desk on the ground floor. You can also book online through our hospital portal.
```

## Tips for Best Results

1. **Be Clear**: State your question clearly
   - Good: "Where is the emergency department?"
   - Okay: "Emergency room location?"

2. **Include Keywords**: Use specific terms like doctor, department, service
   - Good: "Tell me about cardiology doctors"
   - Less specific: "Who treats hearts?"

3. **Be Specific**: Mention the department or service name
   - Good: "Where is the pharmacy?"
   - Too vague: "Where can I get medicine?"

4. **Natural Language**: Speak naturally, the system understands conversational queries
   - "I need help with chest pain" ✓
   - "I have a medical emergency" ✓
   - "Tell me about orthopedic doctors" ✓

## Exit Commands

To end the conversation, say:
- "exit"
- "quit"
- "goodbye"
- "bye"
- "stop"

## Running the System

### Interactive Text Mode
```bash
python main.py --text-mode
```

### Interactive Voice Mode (requires microphone)
```bash
python main.py
```

### Single Query Mode
```bash
python main.py --text-mode --query "Where is the emergency department?"
```

### Demo Mode
```bash
python demo.py
```

## Customization

To add more hospital information:
1. Edit `hospital_data.py` to add doctors, departments, or services
2. Update `config.py` to modify intent keywords
3. Modify `response_generator.py` to change response formats
