"""
Gemini API Key Rotator & Client Manager.
Supports multiple Gemini API keys used in random rotation per request,
with automatic fallback and rotation on rate-limiting (429/ResourceExhausted).
"""

import logging
import os
import random
from typing import Callable, List, Optional
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

logger = logging.getLogger(__name__)



class GeminiKeyRotator:
    def __init__(self, keys: Optional[List[str]] = None, default_model: Optional[str] = None):
        self.default_model = default_model or os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
        self.fallback_models = [
            "gemini-3.5-flash-lite",
            "gemini-2.5-flash",
            "gemini-flash-latest",
            "gemini-2.5-flash-lite",
        ]
        self.keys: List[str] = []

        if keys is not None:
            self.keys = [k.strip() for k in keys if k and k.strip()]
        else:
            self._load_keys_from_env()


    def _load_keys_from_env(self) -> None:
        """
        Load Gemini API keys from environment variables:
        1. GEMINI_API_KEYS (comma, semicolon, or newline separated)
        2. GEMINI_API_KEY (single key)
        3. Any variable matching GEMINI_API_KEY_* (e.g. GEMINI_API_KEY_1, GEMINI_API_KEY_2)
        """
        keys_set = set()

        # 1. Comma/semicolon separated list
        multi_keys = os.environ.get("GEMINI_API_KEYS", "")
        if multi_keys:
            for delimiter in [",", ";", "\n"]:
                multi_keys = multi_keys.replace(delimiter, " ")
            for k in multi_keys.split():
                if k.strip():
                    keys_set.add(k.strip())

        # 2. Single key
        single_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if single_key:
            keys_set.add(single_key)

        # 3. Numbered keys (e.g. GEMINI_API_KEY_1, GEMINI_API_KEY_2)
        for env_var, val in os.environ.items():
            if env_var.startswith("GEMINI_API_KEY_") and val.strip():
                keys_set.add(val.strip())

        self.keys = list(keys_set)

    @property
    def key_count(self) -> int:
        return len(self.keys)

    def get_random_key(self) -> Optional[str]:
        """Return a randomly chosen API key from the active pool."""
        if not self.keys:
            return None
        return random.choice(self.keys)

    def generate_text(self, prompt: str, model_name: Optional[str] = None, **kwargs) -> Optional[str]:
        """
        Generate text using a randomly rotated Gemini API key.
        If a key hits rate limits or errors, automatically retries with another key in the pool.
        """
        if not self.keys:
            logger.debug("No Gemini API keys configured. Skipping LLM request.")
            return None

        model = model_name or self.default_model

        def _call_gemini(key: str, p: str) -> str:
            genai.configure(api_key=key)
            models_to_try = [model] + [m for m in self.fallback_models if m != model]
            last_err = None
            for m_name in models_to_try:
                try:
                    llm = genai.GenerativeModel(m_name)
                    response = llm.generate_content(p, **kwargs)
                    return response.text
                except Exception as ex:
                    last_err = ex
                    if "404" in str(ex) or "not found" in str(ex).lower():
                        continue
                    raise ex
            if last_err:
                raise last_err
            raise RuntimeError("No suitable Gemini model found")

        return self._call_with_fallback(prompt, _call_gemini)

    def _call_with_fallback(self, prompt: str, call_fn: Callable[[str, str], str]) -> Optional[str]:
        """
        Iterate through randomly shuffled keys until one succeeds.
        """
        available_keys = list(self.keys)
        random.shuffle(available_keys)

        last_error = None
        for idx, key in enumerate(available_keys):
            masked_key = f"{key[:4]}...{key[-4:]}" if len(key) > 8 else "***"
            try:
                logger.info(f"Using randomly rotated Gemini Key [{idx+1}/{len(available_keys)}] ({masked_key})")
                return call_fn(key, prompt)
            except Exception as e:
                last_error = e
                logger.warning(
                    f"Gemini API request failed using key {masked_key}: {e}. Rotating to next available key..."
                )

        logger.error(f"All {len(self.keys)} Gemini API keys exhausted or failed: {last_error}")
        return None
