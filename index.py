"""Root FastAPI entry point for Vercel's `app` service.

The backend serves the dashboard and presentation from dist/. Vercel routes
/api/* to the separate api service before this catch-all service.
"""
from backend.app import app
