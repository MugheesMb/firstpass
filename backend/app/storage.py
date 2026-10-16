"""Case storage (memory or Firestore) and file storage (local disk or Cloud Storage).

Cloud Run instances are ephemeral and can scale to several copies, so use
STORE_BACKEND=firestore and FILE_BACKEND=gcs when deployed.
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Optional

from .config import settings
from .models import Case


# ------------------------------------------------------------------ cases
class MemoryCaseStore:
    def __init__(self):
        self._d: dict[str, str] = {}

    def save(self, case: Case) -> None:
        self._d[case.id] = case.model_dump_json()

    def get(self, case_id: str) -> Optional[Case]:
        raw = self._d.get(case_id)
        return Case.model_validate_json(raw) if raw else None

    def list(self, limit: int = 100) -> list[Case]:
        cs = [Case.model_validate_json(r) for r in self._d.values()]
        return sorted(cs, key=lambda c: c.updated_at or "", reverse=True)[:limit]


class FirestoreCaseStore:
    def __init__(self):
        from google.cloud import firestore

        self._col = firestore.Client(project=settings.gcp_project or None).collection(settings.firestore_collection)

    def save(self, case: Case) -> None:
        self._col.document(case.id).set(json.loads(case.model_dump_json()))

    def get(self, case_id: str) -> Optional[Case]:
        snap = self._col.document(case_id).get()
        return Case.model_validate(snap.to_dict()) if snap.exists else None

    def list(self, limit: int = 100) -> list[Case]:
        from google.cloud import firestore

        q = self._col.order_by("updated_at", direction=firestore.Query.DESCENDING).limit(limit)
        return [Case.model_validate(s.to_dict()) for s in q.stream()]


# ------------------------------------------------------------------ files
class LocalFileStore:
    def __init__(self):
        self.root = settings.local_file_dir
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, key: str, data: bytes) -> None:
        p = self.root / key
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get(self, key: str) -> Optional[bytes]:
        p = self.root / key
        return p.read_bytes() if p.exists() else None


class GcsFileStore:
    def __init__(self):
        from google.cloud import storage

        self._b = storage.Client(project=settings.gcp_project or None).bucket(settings.gcs_bucket)

    def put(self, key: str, data: bytes) -> None:
        self._b.blob(key).upload_from_string(data)

    def get(self, key: str) -> Optional[bytes]:
        blob = self._b.blob(key)
        return blob.download_as_bytes() if blob.exists() else None


@lru_cache(maxsize=1)
def cases():
    return FirestoreCaseStore() if settings.store_backend == "firestore" else MemoryCaseStore()


@lru_cache(maxsize=1)
def files():
    return GcsFileStore() if settings.file_backend == "gcs" else LocalFileStore()
