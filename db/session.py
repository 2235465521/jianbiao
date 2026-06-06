from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from config.settings import settings

# Big Tech standard: connection pool initialized at application startup
# It maintains persistent connections to MySQL
engine = create_engine(
    settings.database_url,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    echo=settings.DB_ECHO,
    pool_pre_ping=True  # Checks connection liveness before using it from the pool
)

# Factory to generate new sessions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_session():
    """Dependency for delivering DB sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
