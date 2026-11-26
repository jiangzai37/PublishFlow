from collections.abc import Iterator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

settings = get_settings()
DATABASE_PATH = settings.data_dir / "publishflow.db"
engine = create_engine(
    f"sqlite:///{DATABASE_PATH}",
    connect_args={"check_same_thread": False, "timeout": 30},
)


@event.listens_for(engine, "connect")
def _configure_sqlite(dbapi_connection, _) -> None:
    dbapi_connection.execute("PRAGMA foreign_keys=ON")
    dbapi_connection.execute("PRAGMA journal_mode=WAL")
    dbapi_connection.execute("PRAGMA busy_timeout=30000")


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate_queue_schema() -> None:
    additions = {
        "drafts": {
            "content_type": "VARCHAR(16) NOT NULL DEFAULT 'article'",
            "video_path": "VARCHAR(500)",
            "video_duration": "INTEGER",
            "video_width": "INTEGER",
            "video_height": "INTEGER",
            "video_partition": "VARCHAR(120)",
            "video_collection": "VARCHAR(120)",
        },
        "publish_tasks": {
            "max_retries": "INTEGER NOT NULL DEFAULT 1",
            "next_retry_at": "DATETIME",
            "schedule_plan_id": "INTEGER",
            "run_key": "VARCHAR(120)",
            "idempotency_key": "VARCHAR(120)",
            "snapshot_json": "TEXT",
            "submission_uncertain": "BOOLEAN NOT NULL DEFAULT 0",
            "content_type": "VARCHAR(16) NOT NULL DEFAULT 'article'",
        },
        "presets": {
            "is_builtin": "BOOLEAN NOT NULL DEFAULT 0",
            "updated_at": "DATETIME",
        },
        "schedule_plans": {
            "authorized_fingerprint": "VARCHAR(64)",
        },
    }
    with engine.begin() as connection:
        for table, columns in additions.items():
            existing = {
                row["name"]
                for row in connection.execute(text(f"PRAGMA table_info({table})")).mappings()
            }
            for name, definition in columns.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_publish_tasks_run_key "
                "ON publish_tasks(run_key) WHERE run_key IS NOT NULL"
            )
        )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_publish_tasks_idempotency_key "
                "ON publish_tasks(idempotency_key) WHERE idempotency_key IS NOT NULL"
            )
        )


def init_db() -> None:
    from app.core.typesetting.presets import load_presets
    from app.storage.models import Base, Preset

    Base.metadata.create_all(engine)
    _migrate_queue_schema()
    with SessionLocal.begin() as db:
        for preset_data in load_presets():
            existing = db.get(Preset, preset_data["id"])
            if existing is None:
                db.add(Preset(**preset_data, is_builtin=True))
            elif existing.id in {"fresh", "editorial"}:
                existing.is_builtin = True
