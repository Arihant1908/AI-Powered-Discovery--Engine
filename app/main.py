from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.config import settings
from app.routers import meta, dashboard, upload, insights

@asynccontextmanager
async def lifespan(app: FastAPI):
    from scripts.validate_data import validate_data
    from app.services.data_store import load_data
    # Validate datasets at startup (fails loudly if invalid)
    validate_data()
    # Preload datasets once into in-memory store
    load_data()
    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.1.0",
    lifespan=lifespan,
)

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Error Handlers (Rule 6: Every API error returns JSON: {"error": {"code": "...", "message": "..."}})
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    code = f"HTTP_{exc.status_code}"
    message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "message": message}},
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "VALIDATION_ERROR", "message": str(exc)}},
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_SERVER_ERROR", "message": "An unexpected error occurred."}},
    )

@app.get("/health", tags=["system"])
def health_check():
    return {"status": "ok"}

# Include routers
app.include_router(meta.router)
app.include_router(dashboard.router)
app.include_router(upload.router)
app.include_router(insights.router)

# Mount static assets
static_dir = settings.BASE_DIR / "frontend" / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Serve Frontend Pages
pages_dir = settings.BASE_DIR / "frontend" / "pages"

@app.get("/", tags=["frontend"])
def serve_dashboard():
    return FileResponse(pages_dir / "dashboard.html")

@app.get("/upload", tags=["frontend"])
def serve_upload():
    return FileResponse(pages_dir / "upload.html")

@app.get("/insights", tags=["frontend"])
def serve_insights():
    return FileResponse(pages_dir / "insights.html")
