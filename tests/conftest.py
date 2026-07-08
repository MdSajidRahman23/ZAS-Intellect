import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEST_DB = ROOT / "test_zas_intellect.db"
if TEST_DB.exists():
    TEST_DB.unlink()

os.environ.setdefault("DATABASE_URL", f"sqlite:///{TEST_DB.as_posix()}")
os.environ.setdefault("AI_PROVIDER", "offline")
os.environ.setdefault("STT_PROVIDER", "browser")
os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("PRODUCTION_MODE", "false")
os.environ.setdefault("SHOW_DEMO_CREDENTIALS", "true")
os.environ.setdefault("ENABLE_MEDIAPIPE_PROCTORING", "false")
