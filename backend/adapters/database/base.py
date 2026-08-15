from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.config.settings import get_database_url

engine = create_engine(get_database_url(sync=True), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


def get_session():
    return SessionLocal()
