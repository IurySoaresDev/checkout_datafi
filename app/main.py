import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import create_tables, check_db_connection
from app.routers import webhook_router, access_router

settings = get_settings()

logging.basicConfig(
    level=logging.INFO if settings.ENVIRONMENT == "production" else logging.DEBUG,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Iniciando aplicação...")

    db_ok = await check_db_connection()
    if db_ok:
        try:
            await create_tables()
        except Exception as exc:
            logger.warning("Não foi possível criar/verificar tabelas: %s", exc)
    else:
        logger.warning(
            "⚠️  Banco de dados não disponível no startup. "
            "As rotas que dependem do banco retornarão erro até a conexão ser estabelecida. "
            "Configure DATABASE_URL no .env quando o banco estiver pronto."
        )

    logger.info("Aplicação pronta.")
    yield
    logger.info("Encerrando aplicação.")


app = FastAPI(
    title="GG Checkout + AbacatePay — Controle de Acesso",
    description=(
        "Serviço que recebe webhooks do GG Checkout (gateway AbacatePay) "
        "e libera o acesso do cliente ao sistema após confirmação do pagamento. "
        "Sem tela de login — a página de checkout é do próprio GG Checkout."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.ENVIRONMENT != "production" else [settings.APP_BASE_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhook_router, prefix="/api/v1")
app.include_router(access_router, prefix="/api/v1")


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "environment": settings.ENVIRONMENT}


@app.get("/", tags=["Health"])
async def root():
    return {
        "service": "GG Checkout + AbacatePay",
        "docs": "/docs",
    }
