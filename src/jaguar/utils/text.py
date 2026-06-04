"""
Text analysis utilities for JAGUAR.

Provides readability scoring, text statistics, and content analysis
functions used by the UX and AI detection analyzers.
"""

from __future__ import annotations

import math
import re
from collections import Counter


def count_syllables(word: str) -> int:
    """Estimate syllable count for an English word."""
    word = word.lower().strip()
    if not word:
        return 0
    if len(word) <= 3:
        return 1

    # Remove trailing 'e'
    word = re.sub(r"e$", "", word)

    # Count vowel groups
    vowel_groups = re.findall(r"[aeiouy]+", word)
    count = len(vowel_groups)

    return max(1, count)


def flesch_reading_ease(text: str) -> float:
    """
    Calculate the Flesch Reading Ease score.

    90-100: Very easy (5th grade)
    80-89:  Easy (6th grade)
    70-79:  Fairly easy (7th grade)
    60-69:  Standard (8th-9th grade)
    50-59:  Fairly difficult (10th-12th grade)
    30-49:  Difficult (college)
    0-29:   Very difficult (professional)
    """
    sentences = _split_sentences(text)
    words = _split_words(text)

    if not sentences or not words:
        return 0.0

    num_sentences = len(sentences)
    num_words = len(words)
    num_syllables = sum(count_syllables(w) for w in words)

    if num_sentences == 0 or num_words == 0:
        return 0.0

    score = 206.835 - 1.015 * (num_words / num_sentences) - 84.6 * (num_syllables / num_words)

    return max(0.0, min(100.0, score))


def flesch_kincaid_grade(text: str) -> float:
    """Calculate the Flesch-Kincaid Grade Level."""
    sentences = _split_sentences(text)
    words = _split_words(text)

    if not sentences or not words:
        return 0.0

    num_sentences = len(sentences)
    num_words = len(words)
    num_syllables = sum(count_syllables(w) for w in words)

    if num_sentences == 0 or num_words == 0:
        return 0.0

    grade = 0.39 * (num_words / num_sentences) + 11.8 * (num_syllables / num_words) - 15.59

    return max(0.0, grade)


def vocabulary_diversity(text: str) -> float:
    """
    Calculate type-token ratio (TTR) as a vocabulary diversity measure.

    Returns a value between 0.0 and 1.0.
    Higher values indicate more diverse vocabulary.
    """
    words = _split_words(text)
    if not words:
        return 0.0
    unique = set(w.lower() for w in words)
    return len(unique) / len(words)


def sentence_length_variance(text: str) -> float:
    """
    Calculate the standard deviation of sentence lengths.

    Low variance can indicate AI-generated text (overly uniform sentences).
    """
    sentences = _split_sentences(text)
    if len(sentences) < 2:
        return 0.0

    lengths = [len(_split_words(s)) for s in sentences]
    mean = sum(lengths) / len(lengths)
    variance = sum((length - mean) ** 2 for length in lengths) / len(lengths)
    return math.sqrt(variance)


def word_frequency_analysis(text: str) -> dict[str, int]:
    """Return word frequency counts for the most common words."""
    words = _split_words(text)
    counter = Counter(w.lower() for w in words)
    return dict(counter.most_common(50))


def extract_visible_text(html: str) -> str:
    """
    Extract visible text content from HTML, stripping tags and scripts.

    This is a lightweight extraction without requiring BeautifulSoup,
    useful for quick text analysis.
    """
    # Remove script and style blocks
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode common entities
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&nbsp;", " ").replace("&quot;", '"')
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def detect_boilerplate_ratio(text: str) -> float:
    """
    Estimate the ratio of boilerplate/generic content in text.

    Looks for common filler phrases often seen in AI-generated or template content.
    Returns 0.0 to 1.0.
    """
    boilerplate_phrases = [
        "lorem ipsum",
        "click here",
        "read more",
        "learn more",
        "get started",
        "sign up today",
        "subscribe now",
        "we are passionate",
        "our mission is",
        "state-of-the-art",
        "cutting-edge",
        "game-changing",
        "revolutionary",
        "seamless experience",
        "leverage",
        "synergy",
        "paradigm",
        "ecosystem",
        "holistic approach",
    ]

    text_lower = text.lower()
    words = _split_words(text)
    if not words:
        return 0.0

    hits = sum(1 for phrase in boilerplate_phrases if phrase in text_lower)
    return min(1.0, hits / max(len(boilerplate_phrases) / 3, 1))


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    sentences = re.split(r"[.!?]+\s+", text)
    return [s.strip() for s in sentences if s.strip()]


def _split_words(text: str) -> list[str]:
    """Split text into words."""
    return re.findall(r"\b[a-zA-Z']+\b", text)
