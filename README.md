# IntegraBog

Análisis y visualización de la red de TransMilenio en Bogotá.
Diagnóstico de la red troncal existente y sugerencia de nuevas
troncales basada en la malla vial de OpenStreetMap.

## Estructura del proyecto

```
IntegraBog/
├── src/integrabog/       # Paquete principal
│   ├── api/              # API REST (FastAPI)
│   ├── data/             # Carga de datos geoespaciales
│   ├── graph/            # Grafos macro, micro y multicapa
│   └── routing/          # Algoritmos de diseño de rutas
├── scripts/              # Utilidades de línea de comandos
├── tests/                # Tests automatizados
├── data/
│   ├── raw/              # Datos crudos (GeoJSON)
│   └── processed/        # Datos procesados (GraphML)
├── frontend/             # Interfaz web estática
├── pyproject.toml        # Configuración del proyecto
└── README.md
```

## Requisitos

- Python ≥ 3.13
- [uv](https://docs.astral.sh/uv/) (gestor de paquetes recomendado)

## Instalación

```bash
uv sync
```

O con pip:

```bash
pip install .
```

## Uso

### API REST

```bash
uvicorn integrabog.api.main:app --reload
```

- API: http://localhost:8000/
- Documentación interactiva: http://localhost:8000/docs

### Scripts

```bash
# Construir grafo micro (malla vial desde OSMnx)
python scripts/build_micro.py

# Construir y validar grafo multicapa
python scripts/build_multilayer.py

# Diagnóstico de caso límite (Escuela Militar - San Martín)
python scripts/diagnostico_caso_limite.py

# Identificar pares críticos para nueva troncal
python scripts/validar_pares_criticos.py

# Diagnóstico rápido del grafo macro
python scripts/run_diagnostico.py
```

### Tests

```bash
uv run pytest tests/ -v
```

Solo tests rápidos (sin descarga de datos):

```bash
uv run pytest tests/ -v -m "not slow"
```

## Desarrollo

Para contribuir:

```bash
# Instalar con dependencias de desarrollo
uv sync --group dev

# Linting
uv run ruff check .

# Type checking
uv run mypy src/integrabog/

# Tests con cobertura
uv run pytest tests/ --cov=src/integrabog/ -v
```

## Licencia

MIT
