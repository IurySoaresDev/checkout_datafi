import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class Base(DeclarativeBase):
    pass


# O engine é criado aqui mas NÃO abre conexão ainda.
# A conexão real só acontece na primeira query ou em create_tables().
# pool_pre_ping=True garante que conexões mortas sejam descartadas automaticamente.
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.ENVIRONMENT == "development",
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db() -> AsyncSession:
    """Dependency do FastAPI — entrega uma sessão e faz commit/rollback automático."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_db_connection() -> bool:
    """Testa se o banco está acessível. Retorna True se OK, False caso contrário."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning("Banco de dados inacessível: %s", exc)
        return False


async def create_tables() -> None:
    """
    Cria todas as tabelas definidas nos models (se ainda não existirem).
    Importa os models aqui para garantir que estejam registrados no Base.metadata
    antes de chamar create_all.
    """
    # Importação local para evitar circular imports e garantir registro dos models
    import app.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Tabelas verificadas/criadas com sucesso.")
