"""Configuración compartida de pytest."""

import os

import pytest

import gym_agent.config  # noqa: F401  (carga .env antes de evaluar GEMINI_API_KEY)


def pytest_collection_modifyitems(config, items):
    """Saltea los tests marcados `llm` cuando falta GEMINI_API_KEY."""
    if os.getenv("GEMINI_API_KEY"):
        return
    skip = pytest.mark.skip(reason="falta GEMINI_API_KEY")
    for item in items:
        if "llm" in item.keywords:
            item.add_marker(skip)
