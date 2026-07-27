"""
Módulo API — Punto de entrada HTTP y definición de rutas.

Expone ``app`` (instancia de FastAPI) para que uvicorn la sirva.
"""

from integrabog.api.main import app

__all__ = ["app"]
