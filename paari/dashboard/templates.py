"""Jinja2 template rendering helper."""

from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def render(template_name: str, context: dict) -> str:
    """Render a template to a string (used by stub routes)."""
    template = templates.get_template(template_name)
    return template.render(**context)
