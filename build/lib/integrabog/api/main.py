"""
Punto de entrada de la API de IntegraBog.

Como correrla (desde la raiz del repo, con el venv activo):

    uvicorn integrabog.api.main:app --reload

La primera vez que arranca construye el grafo multicapa completo (tarda
unos segundos si la malla vial ya esta en cache; varios minutos si
OSMnx tiene que descargarla). Mientras el proceso siga corriendo, todas
las peticiones reusan ese mismo grafo en memoria.

Documentacion interactiva automatica una vez arriba: http://localhost:8000/docs
Frontend servido en:                                  http://localhost:8000/
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from integrabog.api.routes import router
from integrabog.api.state import construir_estado

RAIZ_PROYECTO = Path(__file__).resolve().parents[3]
CARPETA_FRONTEND = RAIZ_PROYECTO / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 'startup': se ejecuta una sola vez, antes de aceptar la primera peticion.
    app.state.estado_grafo = construir_estado()
    yield
    # 'shutdown': no hay nada que liberar explicitamente (el grafo vive
    # en memoria de proceso y Python lo limpia solo al terminar).


app = FastAPI(
    title="IntegraBog API",
    description="Diagnostico de la red de TransMilenio y sugerencia de nuevas troncales.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS abierto en desarrollo -- si el frontend se sirve desde otro
# origen/puerto (ej. un live-server aparte) durante pruebas, esto evita
# que el navegador bloquee las llamadas fetch(). En produccion conviene
# restringir 'allow_origins' al dominio real.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(router)

# Sirve el frontend estatico (HTML/JS/CSS) directamente desde la API,
# para que un solo comando (uvicorn) levante todo -- ideal para la
# demostracion en vivo de la sustentacion.
if CARPETA_FRONTEND.exists():
    app.mount("/", StaticFiles(directory=CARPETA_FRONTEND, html=True), name="frontend")
