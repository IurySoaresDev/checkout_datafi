from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Banco de Dados
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/checkout_db"

    # GG Checkout
    GGCHECKOUT_API_KEY: str = ""
    GGCHECKOUT_API_URL: str = "https://www.ggcheckout.com/api"
    GGCHECKOUT_WEBHOOK_SECRET: str = ""

    # JWT
    JWT_SECRET_KEY: str = "troque_por_uma_chave_segura_de_32_caracteres_ou_mais"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # URLs da Aplicação
    APP_BASE_URL: str = "http://localhost:8000"

    # Ambiente
    ENVIRONMENT: str = "development"

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()
