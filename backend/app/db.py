from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.models import Base


def create_session_factory(settings: Settings) -> sessionmaker[Session]:
    data_dir = settings.resolved_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "mirrors").mkdir(parents=True, exist_ok=True)
    url = settings.resolved_database_url()
    connect_args: dict = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        connect_args["timeout"] = 30
    engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True, future=True)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

    Base.metadata.create_all(engine)
    _ensure_columns(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)


def _ensure_columns(engine) -> None:  # type: ignore[no-untyped-def]
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    statements: list[str] = []
    if "repos" in tables and "save_local" not in {column["name"] for column in inspector.get_columns("repos")}:
        default = "TRUE" if engine.dialect.name == "postgresql" else "1"
        statements.append(f"ALTER TABLE repos ADD COLUMN save_local BOOLEAN NOT NULL DEFAULT {default}")
    if "app_settings" in tables and "local_mirror_dir" not in {column["name"] for column in inspector.get_columns("app_settings")}:
        statements.append("ALTER TABLE app_settings ADD COLUMN local_mirror_dir TEXT NOT NULL DEFAULT ''")
    if "app_settings" in tables and "proxy_url" not in {column["name"] for column in inspector.get_columns("app_settings")}:
        statements.append("ALTER TABLE app_settings ADD COLUMN proxy_url TEXT NOT NULL DEFAULT ''")
    bool_default = "FALSE" if engine.dialect.name == "postgresql" else "0"
    if "repos" in tables and "use_proxy" not in {column["name"] for column in inspector.get_columns("repos")}:
        statements.append(f"ALTER TABLE repos ADD COLUMN use_proxy BOOLEAN NOT NULL DEFAULT {bool_default}")
    if "ai_providers" in tables and "use_proxy" not in {column["name"] for column in inspector.get_columns("ai_providers")}:
        statements.append(f"ALTER TABLE ai_providers ADD COLUMN use_proxy BOOLEAN NOT NULL DEFAULT {bool_default}")
    if not statements:
        return
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    db = factory()
    try:
        yield db
    finally:
        db.close()
