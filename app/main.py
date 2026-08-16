from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import BASE_DIR, settings
from .database import init_db
from .routers import auth, documents, extract, subjects

settings.ensure_dirs()
init_db()

app = FastAPI(title="Organizador de PDFs", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(subjects.router)
app.include_router(extract.router)

app.mount("/", StaticFiles(directory=str(BASE_DIR / "app" / "static"), html=True), name="static")
