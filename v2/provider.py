#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Thin multimodal-provider adapter (infrastructure only).

Product logic (tagging pipeline, prompts, schema, taxonomy) depends only on
the ``LLMProvider`` surface: ``chat(system, user_content) -> str``. Any
OpenAI-compatible endpoint/provider can be substituted by pointing the
environment at it — no product changes required.

Environment (see TaggingConfig.from_env):
  V2_API_BASE_URL / API_BASE_URL    e.g. https://llm.gw.dachensky.com
  V2_API_KEY / API_KEY
  V2_MODEL_NAME / MODEL_NAME
  V2_API_RETRIES (default 3), V2_TEMPERATURE (default 0)
"""
from __future__ import annotations

from typing import Protocol


class LLMProvider(Protocol):
    """Minimal surface the V2.1a pipeline needs from a multimodal provider."""

    def chat(self, system: str, user_content: list[dict]) -> str:
        """One completion call; returns the assistant text content."""
        ...


def make_provider(cfg) -> LLMProvider:
    """Build the provider adapter from a TaggingConfig.

    Kept as the single construction point so a different OpenAI-compatible
    provider can be swapped in later without touching product logic.
    """
    from .tagging import ApiClient  # local import: avoid cycle at module load
    return ApiClient(cfg.api_base, cfg.api_key, cfg.model,
                     temperature=cfg.temperature, max_retries=cfg.api_retries)
