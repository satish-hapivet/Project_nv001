#!/usr/bin/env python3
"""Demo script showcasing the Hospital Assistant Robot capabilities."""

from hospital_assistant import HospitalAssistant


def main():
    """Run demo scenarios."""
    print("=" * 60)
    print("HOSPITAL ASSISTANT ROBOT - DEMO")
    print("=" * 60)
    print()
    
    # Create assistant in text mode (no voice dependencies needed)
    assistant = HospitalAssistant(use_voice=False)
    
    # Demo queries
    demo_queries = [
        "Where is the emergency department?",
        "Tell me about cardiology doctors",
        "I need information about the pharmacy",
        "What are the hours for pediatrics?",
        "I have chest pain",
        "Where is the radiology department?",
        "What services do you offer?",
        "How do I schedule an appointment?",
        "Tell me about orthopedic doctors",
        "Where can I find the cafeteria?"
    ]
    
    print("Running demo queries...\n")
    
    for i, query in enumerate(demo_queries, 1):
        print(f"\n--- Query {i} ---")
        print(f"Patient: {query}")
        response = assistant.process_single_query(query)
        print(f"Assistant: {response}")
        print("-" * 60)
    
    print("\n" + "=" * 60)
    print("DEMO COMPLETE")
    print("=" * 60)
    print("\nTo run the assistant interactively in text mode:")
    print("  python main.py --text-mode")
    print("\nTo run with voice (requires microphone and dependencies):")
    print("  python main.py")
    print()


if __name__ == '__main__':
    main()
