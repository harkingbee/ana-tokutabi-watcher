from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ana_tokutabi_watcher.models import Base


def get_engine(database_url: str):  # type: ignore[no-untyped-def]
    # SQLiteファイルの親ディレクトリを作成
    if database_url.startswith("sqlite"):
        # sqlite:///./data/ana_tokutabi.db -> ./data/ana_tokutabi.db
        path_part = database_url.split("sqlite:///")[-1]
        # メモリDBはスキップ
        if path_part and path_part != ":memory:":
            p = Path(path_part)
            if p.parent != Path("."):
                p.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(database_url, echo=False, future=True)
    return engine


def init_db(database_url: str) -> None:
    engine = get_engine(database_url)
    Base.metadata.create_all(engine)


def get_session_factory(database_url: str) -> sessionmaker[Session]:
    engine = get_engine(database_url)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)
