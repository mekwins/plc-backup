"""
AI-powered PLC diff comparison using Azure OpenAI or an OpenAI-compatible endpoint.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.compare.prompts import CONTROLS_ENGINEERING_PROMPT, build_user_prompt
from app.config.schema import AiConfig

logger = logging.getLogger(__name__)

# Profile lookup — allows future addition of domain-specific system prompts
_SYSTEM_PROMPT_PROFILES: Dict[str, str] = {
    "controls-engineering": CONTROLS_ENGINEERING_PROMPT,
}


class AiCompareAdapter:
    """
    Sends PLC diff data to an AI endpoint and returns a structured analysis.

    Parameters
    ----------
    config:
        ``AiConfig`` instance from the application configuration.
    """

    def __init__(self, config: AiConfig) -> None:
        self._config = config
        self._api_key: str = os.environ.get(config.api_key_env, "")
        if not self._api_key:
            logger.warning(
                "AI API key not found in environment variable %s",
                config.api_key_env,
            )

    async def compare(
        self,
        content_a: str,
        content_b: str,
        plc_name: str,
        sections_diff: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Generate an AI-powered comparison report for two L5X versions.

        Parameters
        ----------
        content_a, content_b:
            Text content of the two L5X files being compared.
        plc_name:
            Logical PLC name (used in the prompt for context).
        sections_diff:
            Structured section diff from ``compute_xml_sections_diff``.

        Returns
        -------
        dict
            Parsed AI response with keys: summary, riskLevel, highlights, sections.
        """
        # Compute text diff and truncate to max input chars
        from app.compare.deterministic_diff import compute_text_diff

        diff_text = compute_text_diff(content_a, content_b)

        max_chars = self._config.max_input_chars
        if len(diff_text) > max_chars:
            logger.warning(
                "Diff text (%d chars) exceeds max_input_chars (%d); truncating",
                len(diff_text),
                max_chars,
            )
            diff_text = diff_text[:max_chars] + "\n... [TRUNCATED] ..."

        user_prompt = build_user_prompt(plc_name, sections_diff, diff_text)
        system_prompt = _SYSTEM_PROMPT_PROFILES.get(
            self._config.prompt_profile, CONTROLS_ENGINEERING_PROMPT
        )

        raw_response = await self._call_api(system_prompt, user_prompt)
        return self._parse_response(raw_response)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def _call_api(self, system_prompt: str, user_prompt: str) -> str:
        """POST to the AI endpoint and return the raw text response."""
        headers = {
            "Content-Type": "application/json",
            "api-key": self._api_key,  # Azure OpenAI uses api-key header
            "Authorization": f"Bearer {self._api_key}",  # OpenAI-compatible
        }

        payload = {
            "model": self._config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": self._config.max_tokens,
            "temperature": 0.2,  # Low temperature for deterministic engineering output
            "response_format": {"type": "json_object"},
        }

        # Build URL — Azure and plain OpenAI have different path patterns
        url = _build_api_url(self._config)

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        choices = data.get("choices", [])
        if not choices:
            raise ValueError("AI API returned no choices in response")
        return choices[0]["message"]["content"]

    def _parse_response(self, raw: str) -> Dict[str, Any]:
        """Parse the AI JSON response, returning a safe fallback on failure."""
        try:
            parsed = json.loads(raw)
            # Ensure required keys exist
            return {
                "summary": parsed.get("summary", "No summary provided."),
                "riskLevel": parsed.get("riskLevel", "unknown"),
                "highlights": parsed.get("highlights", []),
                "sections": parsed.get("sections", {}),
            }
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse AI response as JSON: %s", exc)
            return {
                "summary": "AI response could not be parsed.",
                "riskLevel": "unknown",
                "highlights": [],
                "sections": {},
                "raw_response": raw,
            }


def _build_api_url(config: AiConfig) -> str:
    """Build the correct chat completions URL for Azure or standard OpenAI."""
    endpoint = config.endpoint.rstrip("/")
    if config.provider == "azure_openai":
        # Azure OpenAI path: <endpoint>/openai/deployments/<model>/chat/completions?api-version=...
        return (
            f"{endpoint}/openai/deployments/{config.model}"
            f"/chat/completions?api-version=2024-02-01"
        )
    # Standard OpenAI or any compatible endpoint
    return f"{endpoint}/v1/chat/completions"
