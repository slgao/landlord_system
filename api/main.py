from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from db import migrate_to_head
from auth import require_auth
from api.routers import properties, apartments, tenants, contracts, payments

app = FastAPI(
    title="Landlord System API",
    description="REST API for the Hausverwaltung — powers the Streamlit UI and future frontends.",
    version="1.0.0",
)

# CORS — allow Streamlit (8501) and future Next.js (3000) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8501",   # Streamlit dev
        "http://localhost:3000",   # Next.js dev (future)
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers — all /api/* endpoints require authentication
_auth = [Depends(require_auth)]
app.include_router(properties.router, prefix="/api", dependencies=_auth)
app.include_router(apartments.router, prefix="/api", dependencies=_auth)
app.include_router(tenants.router,    prefix="/api", dependencies=_auth)
app.include_router(contracts.router,  prefix="/api", dependencies=_auth)
app.include_router(payments.router,   prefix="/api", dependencies=_auth)


@app.on_event("startup")
def startup():
    migrate_to_head()


@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "docs": "/docs"}


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}
