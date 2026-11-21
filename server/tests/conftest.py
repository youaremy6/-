from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SERVER_DIR.parent
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

PHRASE_PACK = REPO_ROOT / "assets" / "phrases" / "phrases.json"


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        env="test",
        provider_mode="mock",
        media_dir=tmp_path / "media",
        public_base_url="http://testserver",
        phrase_asset_dir=REPO_ROOT / "assets" / "phrases",
        enable_debug_hooks=True,
        cache_ttl_seconds=600,
        signed_url_ttl_seconds=600,
    )


@pytest.fixture()
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture()
def client(app):
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture()
def pack() -> dict:
    return json.loads(PHRASE_PACK.read_text(encoding="utf-8"))
