"""
NEXUS - Free LLM Router
Automatically routes between free LLM providers:
  1. Groq (primary) - Free: 30 req/min, Llama 3.3 70B
  2. Google Gemini (fallback) - Free: 15 req/min, Gemini 2.0 Flash
  3. Ollama (emergency) - Free: local, no limits

If one fails (rate limit, downtime), it falls through to the next.
Total cost: $0
"""

import os
import asyncio
from typing import Optional

from backend.config import settings


class LLMRouter:
    """Routes LLM requests to free providers with automatic fallback"""

    def __init__(self):
        self._groq_client = None
        self._gemini_model = None
        self._ollama_available = False
        self._initialized = False

    async def initialize(self):
        """Initialize all available LLM clients"""
        if self._initialized:
            return

        # Try Groq
        if settings.groq_api_key:
            try:
                from groq import AsyncGroq
                self._groq_client = AsyncGroq(api_key=settings.groq_api_key)
                print("[LLM] Groq client initialized (Llama 3.3 70B, free tier)")
            except ImportError:
                print("[LLM] Groq package not installed, skipping")
            except Exception as e:
                print(f"[LLM] Groq init failed: {e}")

        # Try Gemini
        if settings.gemini_api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=settings.gemini_api_key)
                self._gemini_model = genai.GenerativeModel("gemini-2.0-flash")
                print("[LLM] Gemini client initialized (Gemini 2.0 Flash, free tier)")
            except ImportError:
                print("[LLM] Google GenAI package not installed, skipping")
            except Exception as e:
                print(f"[LLM] Gemini init failed: {e}")

        # Try Ollama
        if settings.ollama_enabled:
            try:
                import ollama as ollama_lib
                # Quick test to see if Ollama is running
                ollama_lib.list()
                self._ollama_available = True
                print(f"[LLM] Ollama available (model: {settings.ollama_model})")
            except Exception:
                print("[LLM] Ollama not available (is it running?)")

        self._initialized = True

        if not self._groq_client and not self._gemini_model and not self._ollama_available:
            print("[LLM] WARNING: No LLM provider available! Set up at least one in .env")

    # Hard per-provider timeout. Anything longer is treated as a hang and the
    # router falls through to the next provider. Prevents one stuck API call
    # from stalling the entire query pipeline (seen: Groq hanging for 100s+).
    PROVIDER_TIMEOUT_SECONDS = 20.0

    async def generate(self, prompt: str, system_prompt: str = "", max_tokens: int = 1024) -> str:
        """
        Generate text using the best available free LLM.
        Tries providers in priority order with automatic fallback.
        Each provider gets at most PROVIDER_TIMEOUT_SECONDS; the next one
        takes over if that's exceeded.
        """
        await self.initialize()

        errors = []

        # Priority order based on settings
        providers = [settings.llm_primary, settings.llm_fallback, settings.llm_emergency]

        for provider in providers:
            try:
                if provider == "groq" and self._groq_client:
                    return await asyncio.wait_for(
                        self._generate_groq(prompt, system_prompt, max_tokens),
                        timeout=self.PROVIDER_TIMEOUT_SECONDS,
                    )
                elif provider == "gemini" and self._gemini_model:
                    return await asyncio.wait_for(
                        self._generate_gemini(prompt, system_prompt, max_tokens),
                        timeout=self.PROVIDER_TIMEOUT_SECONDS,
                    )
                elif provider == "ollama" and self._ollama_available:
                    return await asyncio.wait_for(
                        self._generate_ollama(prompt, system_prompt, max_tokens),
                        timeout=self.PROVIDER_TIMEOUT_SECONDS,
                    )
            except asyncio.TimeoutError:
                errors.append(f"{provider}: timeout after {self.PROVIDER_TIMEOUT_SECONDS}s")
                print(f"[LLM] {provider} hung >{self.PROVIDER_TIMEOUT_SECONDS}s, falling through")
                continue
            except Exception as e:
                msg = str(e)[:200]
                errors.append(f"{provider}: {msg}")
                # Mute the repetitive full Gemini API-key-invalid stack; one line is enough.
                print(f"[LLM] {provider} failed: {msg[:120]}")
                continue

        # All providers failed - return a structured fallback
        return f"[LLM unavailable - errors: {'; '.join(errors)}] Unable to generate response for: {prompt[:100]}"

    async def _generate_groq(self, prompt: str, system_prompt: str, max_tokens: int) -> str:
        """Generate using Groq's free tier (Llama 3.3 70B)"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await self._groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.3,
        )
        return response.choices[0].message.content

    async def _generate_gemini(self, prompt: str, system_prompt: str, max_tokens: int) -> str:
        """Generate using Google Gemini free tier"""
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

        # Gemini's generate_content is synchronous, run in executor
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self._gemini_model.generate_content(
                full_prompt,
                generation_config={"max_output_tokens": max_tokens, "temperature": 0.3},
            )
        )
        return response.text

    async def _generate_ollama(self, prompt: str, system_prompt: str, max_tokens: int) -> str:
        """Generate using Ollama (local, free, no rate limits)"""
        import ollama as ollama_lib

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: ollama_lib.chat(
                model=settings.ollama_model,
                messages=messages,
                options={"num_predict": max_tokens, "temperature": 0.3},
            )
        )
        return response["message"]["content"]

    @property
    def available_providers(self) -> list[str]:
        """List of currently available LLM providers"""
        providers = []
        if self._groq_client:
            providers.append("groq")
        if self._gemini_model:
            providers.append("gemini")
        if self._ollama_available:
            providers.append("ollama")
        return providers


# Global LLM router instance
llm_router = LLMRouter()
