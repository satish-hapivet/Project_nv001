#!/usr/bin/env python3
"""Main entry point for the Hospital Assistant Robot."""

import sys
import argparse
from hospital_assistant import HospitalAssistant


def main():
    """Main function to run the hospital assistant."""
    parser = argparse.ArgumentParser(
        description='Voice-Enabled Hospital Assistant Robot'
    )
    parser.add_argument(
        '--text-mode',
        action='store_true',
        help='Run in text mode instead of voice mode (useful for testing)'
    )
    parser.add_argument(
        '--query',
        type=str,
        help='Process a single query and exit (text mode only)'
    )
    
    args = parser.parse_args()
    
    # Create assistant instance
    use_voice = not args.text_mode
    assistant = HospitalAssistant(use_voice=use_voice)
    
    # Handle single query mode
    if args.query:
        print(f"Query: {args.query}")
        response = assistant.process_single_query(args.query)
        print(f"Response: {response}")
        return 0
    
    # Start interactive mode
    try:
        assistant.start()
        return 0
    except Exception as e:
        print(f"Error running assistant: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
