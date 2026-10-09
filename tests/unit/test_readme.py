"""El README solo menciona rutas y comandos que existen y no lleva secretos (T124, CE-005)."""

import re

import pytest
from dotenv import dotenv_values

from gym_agent.config import REPO_ROOT

README = REPO_ROOT / "README.md"
PREFIJOS = ("scripts/", "app/", "eval/", "docs/", "db/", "data/")
MODULOS_AJENOS = {"venv", "pip", "pytest"}
"""Módulos de Python que no son del repositorio."""


@pytest.fixture(scope="module")
def texto() -> str:
    return README.read_text(encoding="utf-8")


def _rutas(texto: str) -> list[str]:
    """Rutas entre comillas invertidas que empiezan con una carpeta del repositorio."""
    candidatas = re.findall(r"`([^`\s]+)`", texto)
    return [c for c in candidatas if c.startswith(PREFIJOS)]


def test_las_rutas_mencionadas_existen(texto):
    rutas = _rutas(texto)
    assert rutas, "el README no menciona ninguna ruta del repositorio"
    faltan = [r for r in rutas if not (REPO_ROOT / r).exists()]
    assert not faltan, f"rutas del README que no existen: {faltan}"


def test_los_modulos_de_python_mencionados_existen(texto):
    modulos = re.findall(r"python -m ([\w.]+)", texto)
    assert "eval.run_eval" in modulos
    propios = [m for m in modulos if m not in MODULOS_AJENOS]
    faltan = [m for m in propios if not (REPO_ROOT / (m.replace(".", "/") + ".py")).is_file()]
    assert not faltan, f"módulos del README sin archivo: {faltan}"


def test_los_scripts_ejecutados_existen(texto):
    scripts = re.findall(r"python (scripts/[\w./]+\.py)", texto)
    assert scripts, "el README no ejecuta ningún script de scripts/"
    faltan = [s for s in scripts if not (REPO_ROOT / s).is_file()]
    assert not faltan, f"scripts del README que no existen: {faltan}"


@pytest.mark.parametrize("frase", ["Etapa 0", "Etapa 5", "Estado:"])
def test_no_quedan_avisos_de_etapas(texto, frase):
    assert frase not in texto


def test_el_readme_no_contiene_secretos_del_env(texto):
    env = REPO_ROOT / ".env"
    if not env.is_file():
        pytest.skip("no hay .env")
    valores = dotenv_values(env)
    for nombre in ("GEMINI_API_KEY", "AGENTE_RO_PASSWORD"):
        valor = valores.get(nombre)
        if valor:
            assert valor not in texto, f"el README contiene el valor de {nombre}"
