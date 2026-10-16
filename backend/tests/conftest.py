import os
import sys
from pathlib import Path

os.environ.setdefault("AI_MODE", "mock")
os.environ.setdefault("STORE_BACKEND", "memory")
os.environ.setdefault("FILE_BACKEND", "local")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("AI_CACHE", "off")  # each test sees fresh Gemini behaviour; test_cache turns it on
