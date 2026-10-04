import os
import pytest
from src.gemini_rotator import GeminiKeyRotator

def test_load_keys_from_list():
    rotator = GeminiKeyRotator(keys=["KEY_1", "KEY_2", "KEY_3"])
    assert rotator.key_count == 3
    assert set(rotator.keys) == {"KEY_1", "KEY_2", "KEY_3"}

def test_load_keys_from_env_comma_separated(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEYS", "KEY_A, KEY_B, KEY_C")
    rotator = GeminiKeyRotator()
    assert rotator.key_count == 3
    assert "KEY_A" in rotator.keys
    assert "KEY_B" in rotator.keys
    assert "KEY_C" in rotator.keys

def test_load_keys_from_single_env(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "SINGLE_KEY_123")
    rotator = GeminiKeyRotator()
    assert rotator.key_count == 1
    assert rotator.get_random_key() == "SINGLE_KEY_123"

def test_random_key_distribution():
    rotator = GeminiKeyRotator(keys=["KEY_ALPHA", "KEY_BETA", "KEY_GAMMA"])
    sampled = {rotator.get_random_key() for _ in range(50)}
    # Over 50 random draws, all 3 keys should appear
    assert len(sampled) == 3

def test_empty_keys_fallback(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    rotator = GeminiKeyRotator(keys=[])
    assert rotator.key_count == 0
    assert rotator.get_random_key() is None
    assert rotator.generate_text("Hello") is None

def test_key_rotation_on_failure():
    rotator = GeminiKeyRotator(keys=["KEY_1", "KEY_2"])
    attempts = []

    def mock_caller(key, prompt):
        attempts.append(key)
        if len(attempts) == 1:
            raise Exception("429 ResourceExhausted: Quota exceeded")
        return "Generated response successfully"

    result = rotator._call_with_fallback(prompt="Test prompt", call_fn=mock_caller)
    assert result == "Generated response successfully"
    assert len(attempts) == 2
    assert attempts[0] != attempts[1]

