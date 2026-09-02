from __future__ import annotations
import pytest
from vera.intent.auto_reply import AutoReplyDetector


def test_canned_phrase_detection():
    canned = [
        "Thank you for contacting Dr. Meera's Dental Clinic! Our team will respond shortly.",
        "Aapki jaankari ke liye bahut-bahut shukriya. Main aapki yeh sabhi baatein aur sujhaav hamari team tak pahuncha deti hoon.",
        "We have received your message and will get back to you soon.",
        "I am an automated assistant and cannot reply to custom queries.",
    ]

    for msg in canned:
        is_auto, conf, reason = AutoReplyDetector.evaluate(msg, turn_number=1)
        assert is_auto is True
        assert conf >= 0.85


def test_repeated_identical_message_detection():
    msg = "Please call our reception number 9876543210 during working hours."
    is_auto, conf, _ = AutoReplyDetector.evaluate(
        message=msg,
        turn_number=2,
        prior_messages=[msg],
    )
    assert is_auto is True
    assert conf >= 0.95


def test_real_message_not_flagged():
    real = "Yes please send me the abstract and draft the post."
    is_auto, conf, _ = AutoReplyDetector.evaluate(real, turn_number=2)
    assert is_auto is False
    assert conf == 0.0
