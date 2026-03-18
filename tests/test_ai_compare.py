"""
Tests for app.compare.ai_compare — httpx calls are mocked.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
import httpx

from app.compare.ai_compare import AiCompareAdapter, _build_api_url
from app.compare.prompts import build_user_prompt, CONTROLS_ENGINEERING_PROMPT
from app.config.schema import AiConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ai_config():
    return AiConfig(
        provider="azure_openai",
        endpoint="https://example.openai.azure.com/",
        api_key_env="TEST_AI_KEY",
        model="gpt-4.1",
        prompt_profile="controls-engineering",
        max_input_chars=5000,
        max_tokens=500,
    )


MOCK_AI_RESPONSE = {
    "choices": [
        {
            "message": {
                "content": json.dumps(
                    {
                        "summary": "Minor tag value changes detected.",
                        "riskLevel": "low",
                        "highlights": ["Tag Setpoint changed from 50 to 55"],
                        "sections": {
                            "tags": {"changed": 1, "details": "Setpoint modified"}
                        },
                    }
                )
            }
        }
    ]
}


# ---------------------------------------------------------------------------
# URL builder tests
# ---------------------------------------------------------------------------

def test_azure_url_format():
    cfg = AiConfig(
        provider="azure_openai",
        endpoint="https://myendpoint.openai.azure.com/",
        api_key_env="KEY",
        model="gpt-4.1",
        prompt_profile="controls-engineering",
        max_input_chars=1000,
        max_tokens=100,
    )
    url = _build_api_url(cfg)
    assert "openai/deployments/gpt-4.1/chat/completions" in url
    assert "api-version" in url


def test_openai_url_format():
    cfg = AiConfig(
        provider="openai",
        endpoint="https://api.openai.com",
        api_key_env="KEY",
        model="gpt-4o",
        prompt_profile="controls-engineering",
        max_input_chars=1000,
        max_tokens=100,
    )
    url = _build_api_url(cfg)
    assert url == "https://api.openai.com/v1/chat/completions"


# ---------------------------------------------------------------------------
# Prompt builder tests
# ---------------------------------------------------------------------------

def test_build_user_prompt_contains_plc_name():
    sections_diff = {"programs": {"added": 1, "removed": 0, "modified": 0}}
    prompt = build_user_prompt("Line01-CellA", sections_diff, "--- old\n+++ new\n")
    assert "Line01-CellA" in prompt


def test_build_user_prompt_contains_diff_excerpt():
    prompt = build_user_prompt("PLC1", {}, "--- a\n+++ b\n+new line\n")
    assert "+new line" in prompt


def test_system_prompt_mentions_risk():
    assert "risk" in CONTROLS_ENGINEERING_PROMPT.lower()


def test_system_prompt_mentions_safety():
    assert "safety" in CONTROLS_ENGINEERING_PROMPT.lower()


# ---------------------------------------------------------------------------
# AiCompareAdapter.compare tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_compare_returns_structured_result(ai_config):
    """compare() returns dict with expected keys when AI call succeeds."""
    import os
    os.environ["TEST_AI_KEY"] = "fake-key"

    mock_response = MagicMock()
    mock_response.json.return_value = MOCK_AI_RESPONSE
    mock_response.raise_for_status = MagicMock()

    with patch("app.compare.ai_compare.httpx.AsyncClient") as MockClient:
        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_response)
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        adapter = AiCompareAdapter(ai_config)
        result = await adapter.compare(
            content_a="<xml>old</xml>",
            content_b="<xml>new</xml>",
            plc_name="TestPLC",
            sections_diff={"tags": {"added": 0, "removed": 0, "modified": 1}},
        )

    assert "summary" in result
    assert "riskLevel" in result
    assert result["riskLevel"] == "low"
    assert "highlights" in result


@pytest.mark.asyncio
async def test_compare_truncates_large_diff(ai_config):
    """Diff text exceeding max_input_chars is truncated before sending."""
    import os
    os.environ["TEST_AI_KEY"] = "fake-key"

    mock_response = MagicMock()
    mock_response.json.return_value = MOCK_AI_RESPONSE
    mock_response.raise_for_status = MagicMock()

    captured_payloads = []

    async def fake_post(url, json=None, headers=None):
        captured_payloads.append(json)
        return mock_response

    with patch("app.compare.ai_compare.httpx.AsyncClient") as MockClient:
        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(side_effect=fake_post)
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        # content_a and content_b differ by a very large amount
        long_content_b = "x" * 100000
        adapter = AiCompareAdapter(ai_config)
        await adapter.compare(
            content_a="short",
            content_b=long_content_b,
            plc_name="TestPLC",
            sections_diff={},
        )

    # The user message should contain the truncation marker
    assert captured_payloads
    user_content = captured_payloads[0]["messages"][1]["content"]
    # Diff excerpt in prompt is capped at max_input_chars (5000)
    assert len(user_content) < 100000 + 2000  # some headroom for prompt boilerplate


@pytest.mark.asyncio
async def test_compare_handles_invalid_json_response(ai_config):
    """Invalid JSON from AI is handled gracefully and returns error key."""
    import os
    os.environ["TEST_AI_KEY"] = "fake-key"

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "not valid json {{ at all"}}]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("app.compare.ai_compare.httpx.AsyncClient") as MockClient:
        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_response)
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        adapter = AiCompareAdapter(ai_config)
        result = await adapter.compare(
            content_a="a",
            content_b="b",
            plc_name="TestPLC",
            sections_diff={},
        )

    assert result["summary"] == "AI response could not be parsed."
    assert "raw_response" in result
