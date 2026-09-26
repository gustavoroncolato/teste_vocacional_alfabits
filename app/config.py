"""Configuração via variáveis de ambiente (arquivo .env em desenvolvimento)."""
import os
import re
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "sim", "on"}


@dataclass(frozen=True)
class Settings:
    # ---- LLM (qualquer API compatível com OpenAI: OpenAI, Gemini, Groq, OpenRouter...)
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    llm_timeout: float = float(os.getenv("LLM_TIMEOUT", "40"))
    llm_workers: int = int(os.getenv("LLM_WORKERS", "20"))  # participantes processados em paralelo
    llm_max_concurrency: int = int(os.getenv("LLM_MAX_CONCURRENCY", "40"))  # chamadas simultâneas ao LLM
    llm_json_mode: bool = _bool("LLM_JSON_MODE", True)
    # Modelos que "pensam" (gpt-oss, qwen3): low/medium/high. Vazio = não envia (modelos comuns).
    llm_reasoning_effort: str = os.getenv("LLM_REASONING_EFFORT", "").strip().lower()
    # Simula o LLM (sem gastar crédito) - teste de carga local
    llm_mock: bool = _bool("LLM_MOCK")
    llm_mock_delay: float = float(os.getenv("LLM_MOCK_DELAY", "1.5"))

    # ---- Organização
    org_name: str = os.getenv("ORG_NAME", "Alfabits")
    # WhatsApp da Alfabits (só dígitos, com 55). Usado no botão "Quero conversar": a PESSOA manda a mensagem.
    org_whatsapp: str = re.sub(r"\D", "", os.getenv("ORG_WHATSAPP", ""))
    org_regiao: str = os.getenv("ORG_REGIAO", "Pirapozinho - SP, região de Presidente Prudente")
    public_url: str = os.getenv("PUBLIC_URL", "").rstrip("/")  # ex.: https://teste.alfabits.com.br

    # ---- Geral
    database_path: str = os.getenv("DATABASE_PATH", "data/teste_vocacional.db")
    admin_token: str = os.getenv("ADMIN_TOKEN", "")
    # login da tela /admin (vazio = tela desativada)
    admin_user: str = os.getenv("ADMIN_USER", "")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "")
    start_workers: bool = _bool("START_WORKERS", True)


settings = Settings()
