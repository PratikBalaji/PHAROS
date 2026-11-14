"""Full FastAPI API entry point for Vercel's `api` service.

Share the same route implementation as local development: health, drafts,
approval, broadcast, audit, notifications, and live-data adapters.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app import app
