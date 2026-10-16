"""Runtime configuration, all from environment variables (see .env.example)."""
import os
from dataclasses import dataclass, field
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # "mock" uses ground-truth sidecar files (offline testing); "gemini" calls Vertex AI.
    ai_mode: str = field(default_factory=lambda: os.getenv("AI_MODE", "mock"))
    gcp_project: str = field(default_factory=lambda: os.getenv("GOOGLE_CLOUD_PROJECT", ""))
    # Gemini 3.x models are served from the "global" Vertex AI location.
    gcp_location: str = field(default_factory=lambda: os.getenv("GOOGLE_CLOUD_LOCATION", "global"))
    # Keep model ids in config: preview models change. Check availability in your project.
    model_extract: str = field(default_factory=lambda: os.getenv("MODEL_EXTRACT", "gemini-3.8-flash"))
    model_reason: str = field(default_factory=lambda: os.getenv("MODEL_REASON", "gemini-3.1-pro-preview"))
    model_reason_fallback: str = field(default_factory=lambda: os.getenv("MODEL_REASON_FALLBACK", "gemini-3.8-flash"))
    # Extraction needs reading, not deep reasoning: low thinking is much faster. "" = model default.
    thinking_extract: str = field(default_factory=lambda: os.getenv("THINKING_EXTRACT", "low"))
    # Short yes/no wording comparisons do not need deep reasoning either.
    thinking_judge: str = field(default_factory=lambda: os.getenv("THINKING_JUDGE", "low"))
    max_output_tokens: int = field(default_factory=lambda: int(os.getenv("MAX_OUTPUT_TOKENS", "16384")))
    request_timeout_s: int = field(default_factory=lambda: int(os.getenv("REQUEST_TIMEOUT_S", "180")))
    render_dpi: int = field(default_factory=lambda: int(os.getenv("RENDER_DPI", "150")))

    # Storage: "memory"+"local" for development; "firestore"+"gcs" on Cloud Run.
    store_backend: str = field(default_factory=lambda: os.getenv("STORE_BACKEND", "memory"))
    # Own collection name so FirstPass never mixes with other apps in the same Firebase project.
    firestore_collection: str = field(default_factory=lambda: os.getenv("FIRESTORE_COLLECTION", "firstpass_cases"))
    file_backend: str = field(default_factory=lambda: os.getenv("FILE_BACKEND", "local"))
    local_file_dir: Path = field(default_factory=lambda: Path(os.getenv("LOCAL_FILE_DIR", "/tmp/firstpass-files")))
    gcs_bucket: str = field(default_factory=lambda: os.getenv("GCS_BUCKET", ""))

    demo_dir: Path = field(
        default_factory=lambda: Path(os.getenv("DEMO_DIR", str(Path(__file__).resolve().parent.parent / "demo_cases")))
    )
    # Extra folders of generated cases to list in the app, e.g. ../data/testset (comma-separated).
    # Defaults to the repo's test set when it exists (local development); absent in the Docker image.
    extra_case_dirs: list[Path] = field(
        default_factory=lambda: [Path(p) for p in os.getenv(
            "EXTRA_CASE_DIRS", str(Path(__file__).resolve().parents[2] / "data" / "testset")).split(",") if p]
    )
    allow_origins: list[str] = field(
        default_factory=lambda: [o for o in os.getenv("ALLOW_ORIGINS", "http://localhost:5173").split(",") if o]
    )

    @property
    def use_gemini(self) -> bool:
        return self.ai_mode == "gemini"


settings = Settings()
