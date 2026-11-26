import os
import shutil
import tempfile
from pathlib import Path

import pytest

# Environment must be set before test modules import app.config.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_TEST_ROOT = _PROJECT_ROOT / "artifacts" / "test-storage"
_TEST_ROOT.mkdir(parents=True, exist_ok=True)
_TEST_STORAGE = Path(tempfile.mkdtemp(prefix="publishflow-tests-", dir=_TEST_ROOT))
os.environ["DATA_DIR"] = str(_TEST_STORAGE)
os.environ["UPLOAD_DIR"] = str(_TEST_STORAGE / "uploads")
os.environ["ALLOWED_HOSTS"] = "testserver,127.0.0.1,localhost"
os.environ["MODEL_BASE_URL"] = ""
os.environ["MODEL_API_KEY"] = ""
os.environ["ENCRYPTION_KEY"] = ""
os.environ["IMAGE_BASE_URL"] = ""
os.environ["IMAGE_API_KEY"] = ""


@pytest.fixture(scope="session", autouse=True)
def clean_test_storage():
    from app.storage.database import engine, init_db

    init_db()
    yield
    engine.dispose()
    shutil.rmtree(_TEST_STORAGE, ignore_errors=True)
