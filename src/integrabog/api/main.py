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
    app.state.estado_grafo = construir_estado()
    yield


app = FastAPI(
    title="IntegraBog API",
    description="Diagnostico de la red de TransMilenio y sugerencia de nuevas troncales.",
    version="0.1.0",
    lifespan=lifespan,
)

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
