# Voice-Enabled Hospital Assistant Robot

The system is a voice‑enabled hospital assistant robot that serves as a face‑to‑face audio agent. Using AI‑driven voice navigation, it listens, understands, and responds to patient queries about services, doctors, departments, and emergencies. It integrates speech recognition, NLP, hospital systems, and text‑to‑speech for real‑time communication.

## Features

- **Speech Recognition**: Captures and processes voice input from patients
- **Natural Language Processing**: Understands patient queries and extracts intent
- **Hospital Knowledge Base**: Comprehensive information about doctors, departments, services, and emergencies
- **Text-to-Speech**: Converts responses to natural-sounding voice output
- **Real-time Communication**: Provides instant responses to patient queries

## System Architecture

The system consists of the following modules:

1. **Speech Recognition Module** (`speech_recognition_module.py`): Handles audio input using the SpeechRecognition library
2. **NLP Module** (`nlp_module.py`): Processes queries and detects user intent
3. **Hospital Data** (`hospital_data.py`): Contains hospital information database
4. **Response Generator** (`response_generator.py`): Creates appropriate responses based on intent
5. **Text-to-Speech Module** (`text_to_speech_module.py`): Converts text responses to audio
6. **Hospital Assistant** (`hospital_assistant.py`): Main controller integrating all modules
7. **Configuration** (`config.py`): System settings and parameters

## Installation

### Prerequisites

- Python 3.7 or higher
- Microphone (for voice input)
- Speakers (for voice output)

### Install Dependencies

```bash
pip install -r requirements.txt
```

**Note**: On Linux, you may need to install additional system packages:

```bash
# For Ubuntu/Debian
sudo apt-get install python3-pyaudio portaudio19-dev espeak

# For Fedora/RHEL
sudo dnf install python3-pyaudio portaudio-devel espeak
```

## Usage

### Voice Mode (Default)

Run the assistant in voice mode with microphone input:

```bash
python main.py
```

The assistant will:
1. Greet you
2. Listen for your voice input
3. Process your query
4. Respond with voice output
5. Continue until you say "exit" or "goodbye"

### Text Mode

Run in text mode for testing without a microphone:

```bash
python main.py --text-mode
```

### Single Query Mode

Process a single query and exit (useful for testing):

```bash
python main.py --text-mode --query "Where is the emergency department?"
```

## Query Examples

The assistant can handle various types of queries:

### Doctor Information
- "Who are the cardiologists?"
- "I need a pediatric doctor"
- "Show me neurology doctors"

### Department Information
- "Where is the cardiology department?"
- "What are the hours for pediatrics?"
- "Tell me about the emergency department"

### Services
- "Where is the pharmacy?"
- "What imaging services do you offer?"
- "I need to get lab work done"

### Emergencies
- "I have a medical emergency"
- "What should I do for chest pain?"
- "I need an ambulance"

### General Information
- "What are your visiting hours?"
- "How do I schedule an appointment?"
- "Where can I find the cafeteria?"

## Configuration

Edit `config.py` to customize:

- Speech recognition settings (timeout, energy threshold)
- Text-to-speech settings (rate, volume)
- Assistant behavior and messages
- Intent detection keywords

## Hospital Data

The hospital knowledge base (`hospital_data.py`) contains:

- **Doctors**: Information about specialists in various departments
- **Departments**: Location, hours, and contact information
- **Services**: Laboratory, pharmacy, imaging, and other facilities
- **Emergency Information**: Guidance for various emergency situations

To customize the data for your hospital, edit the `HOSPITAL_DATA` dictionary in `hospital_data.py`.

## Architecture Details

### Intent Detection

The NLP module uses keyword matching to detect user intent:
- **doctor**: Queries about doctors and specialists
- **department**: Queries about hospital departments
- **service**: Queries about hospital services
- **emergency**: Emergency-related queries
- **appointment**: Appointment scheduling
- **hours**: Operating hours queries
- **location**: Location and directions

### Response Generation

The response generator creates contextual responses based on:
1. Detected intent
2. Extracted entities (departments, services, specializations)
3. Original query text

## Development

### Project Structure

```
Project_nv001/
├── main.py                          # Entry point
├── hospital_assistant.py            # Main controller
├── speech_recognition_module.py     # Speech input
├── text_to_speech_module.py         # Voice output
├── nlp_module.py                    # Natural language processing
├── response_generator.py            # Response creation
├── hospital_data.py                 # Hospital information
├── config.py                        # Configuration
├── requirements.txt                 # Dependencies
└── README.md                        # Documentation
```

### Adding New Features

1. **Add new intents**: Update `INTENT_KEYWORDS` in `config.py`
2. **Add hospital data**: Update `HOSPITAL_DATA` in `hospital_data.py`
3. **Customize responses**: Modify methods in `response_generator.py`

## Troubleshooting

### Microphone Issues

If the microphone is not working:
1. Check system microphone permissions
2. Adjust `ENERGY_THRESHOLD` in `config.py`
3. Test with `--text-mode` first

### Speech Recognition Errors

If speech recognition is not accurate:
1. Speak clearly and at a moderate pace
2. Reduce background noise
3. Adjust `SPEECH_RECOGNITION_TIMEOUT` in `config.py`

### Text-to-Speech Issues

If TTS is not working:
1. Check if espeak is installed (Linux)
2. The system will fall back to text-only output if TTS fails

## License

This project is provided as-is for educational and demonstration purposes.

## Contributing

To contribute to this project:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## Support

For issues or questions, please open an issue on the project repository.
