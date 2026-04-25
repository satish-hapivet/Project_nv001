"""
NIMS Hospital Voice Assistant – Hallucination Filter
------------------------------------------------------
Detects and rejects hallucinated Whisper transcripts caused by:
  - Background noise interpreted as speech
  - Audio artifacts generating repetitive patterns
  - VAD false positives on ambient sounds

Rejects before NLU to save API calls.
Ported from the proven voice_agent hallucination_filter.
"""
import re
import logging
from typing import Tuple

logger = logging.getLogger(__name__)


class HallucinationFilter:
    """
    Detects Whisper hallucination patterns in transcribed text.

    Signatures:
      1. Known hallucination phrases (YouTube outros, etc.)
      2. Excessive word repetition (>60% repeated)
      3. Repeated 3-word phrases (3+ occurrences)
      4. Too few unique meaningful words in long text
    """

    KNOWN_HALLUCINATIONS = [
        r"thank you for watching",
        r"please subscribe",
        r"like and subscribe",
        r"see you next time",
        r"don't forget to",
        r"thanks for listening",
        r"music",
        r"applause",
        r"silence",
        r"thank you very much for watching",
        r"please like and subscribe",
        r"i'll see you in the next",
        r"subtitles by",
        r"translated by",
        r"copyright",
        r"you$",
    ]

    MIN_UNIQUE_WORDS = 3
    MAX_REPETITION_RATIO = 0.6

    FILLER_WORDS = {
        "i", "you", "me", "we", "he", "she", "it", "the", "a", "an",
        "is", "are", "am", "was", "were", "be", "been", "being",
        "do", "does", "did", "don't", "doesn't", "didn't",
        "have", "has", "had", "to", "of", "in", "on", "at", "for",
        "and", "or", "but", "so", "um", "uh", "hmm", "oh", "ah",
        "yeah", "yes", "no", "ok", "okay", "like", "just", "really",
        "going", "want", "know", "think", "that", "this", "what",
    }

    def __init__(self):
        self._patterns = [
            re.compile(p, re.IGNORECASE) for p in self.KNOWN_HALLUCINATIONS
        ]

    def is_valid(self, text: str) -> Tuple[bool, str]:
        """
        Check if transcript is genuine (not hallucinated).
        Returns (is_valid, reason).
        """
        if not text or not text.strip():
            return False, "empty_text"

        cleaned = re.sub(r"\s+", " ", text.strip())
        cleaned = re.sub(r"[.!?,]{2,}", ".", cleaned)

        # Check 1: Known hallucination phrases
        for pattern in self._patterns:
            if pattern.search(cleaned):
                return False, "known_hallucination"

        words = cleaned.lower().split()

        # Check 2: Excessive word repetition
        if len(words) > 5:
            ratio = self._repetition_ratio(words)
            if ratio > self.MAX_REPETITION_RATIO:
                return False, f"excessive_repetition ({ratio:.0%})"

        # Check 3: Repeated phrases
        if self._has_repeated_phrases(words, min_phrase_len=3, min_repeats=3):
            return False, "repeated_phrases"

        # Check 4: Too few unique meaningful words
        unique = self._count_unique_meaningful(words)
        if len(words) > 10 and unique < self.MIN_UNIQUE_WORDS:
            return False, f"low_vocabulary ({unique} unique words)"

        return True, "passed"

    @staticmethod
    def _repetition_ratio(words: list) -> float:
        if not words:
            return 0.0
        counts: dict = {}
        for w in words:
            counts[w] = counts.get(w, 0) + 1
        repeated = sum(c - 1 for c in counts.values() if c > 1)
        return repeated / len(words)

    @staticmethod
    def _has_repeated_phrases(
        words: list, min_phrase_len: int = 3, min_repeats: int = 3
    ) -> bool:
        if len(words) < min_phrase_len * min_repeats:
            return False
        phrases: dict = {}
        for i in range(len(words) - min_phrase_len + 1):
            phrase = " ".join(words[i : i + min_phrase_len])
            phrases[phrase] = phrases.get(phrase, 0) + 1
            if phrases[phrase] >= min_repeats:
                return True
        return False

    def _count_unique_meaningful(self, words: list) -> int:
        meaningful = set()
        for w in words:
            w_lower = w.lower()
            if w_lower not in self.FILLER_WORDS and len(w_lower) > 1:
                meaningful.add(w_lower)
        return len(meaningful)


# ── Module-level singleton ──────────────────────────────────────────────

_filter = HallucinationFilter()


def is_valid_transcript(text: str) -> Tuple[bool, str]:
    """Quick check: (is_valid, reason)."""
    return _filter.is_valid(text)
