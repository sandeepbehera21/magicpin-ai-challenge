from __future__ import annotations
import pytest
from vera.intent.classifier import IntentClassifier, IntentKind


def test_multilingual_intent_classification():
    cases = [
        ("yes", IntentKind.YES),
        ("haan", IntentKind.YES),
        ("theek hai", IntentKind.YES),
        ("chalega", IntentKind.YES),
        ("no", IntentKind.NO),
        ("nahi", IntentKind.NO),
        ("nahi chahiye", IntentKind.NO),
        ("stop", IntentKind.STOP),
        ("mat bhejo", IntentKind.STOP),
        ("don't message me", IntentKind.STOP),
        ("useless spam", IntentKind.STOP),
        ("later", IntentKind.LATER),
        ("baad mein", IntentKind.LATER),
        ("abhi nahi", IntentKind.LATER),
        ("busy now", IntentKind.LATER),
        ("join", IntentKind.JOIN_INTENT),
        ("join karna hai", IntentKind.JOIN_INTENT),
        ("i want to join", IntentKind.JOIN_INTENT),
        ("let's do it", IntentKind.ACTION_REQUEST),
        ("lets do it", IntentKind.ACTION_REQUEST),
        ("send it", IntentKind.ACTION_REQUEST),
        ("send karo", IntentKind.ACTION_REQUEST),
        ("bhejo", IntentKind.ACTION_REQUEST),
        ("kar dijiye", IntentKind.ACTION_REQUEST),
        ("how much?", IntentKind.PRICE_REQUEST),
        ("kitna cost hai?", IntentKind.PRICE_REQUEST),
        ("pricing kya hai?", IntentKind.PRICE_REQUEST),
        ("send details", IntentKind.DETAIL_REQUEST),
        ("details bhejo", IntentKind.DETAIL_REQUEST),
        ("can you help with GST filing?", IntentKind.IRRELEVANT),
        ("what is my current Google rank?", IntentKind.QUESTION),
    ]

    for text, expected_intent in cases:
        intent, conf, reason = IntentClassifier.classify(text)
        assert intent == expected_intent, f"Failed for '{text}': got {intent}, expected {expected_intent}"
        assert conf > 0.5
