"""
Configurazione centralizzata per il Trading Agent.
Tutte le impostazioni sono gestite qui per facilitare manutenzione e deploy.
"""

import os
from dataclasses import dataclass, field
from typing import List
from dotenv import load_dotenv

load_dotenv()


@dataclass
class TradingConfig:
    """Configurazione principale del trading bot."""

    # === API Keys ===
    binance_api_key: str = field(default_factory=lambda: os.getenv("BINANCE_API_KEY", ""))
    binance_api_secret: str = field(default_factory=lambda: os.getenv("BINANCE_API_SECRET", ""))
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    cmc_api_key: str = field(default_factory=lambda: os.getenv("CMC_PRO_API_KEY", ""))
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", ""))

    # === Trading Settings ===
    testnet: bool = field(default_factory=lambda: os.getenv("TESTNET", "true").lower() == "true")
    tickers: List[str] = field(default_factory=lambda: os.getenv("TICKERS", "BTC,ETH,SOL").split(","))
    
    # === Loop Settings ===
    # IMPORTANTE: Allineato a 15 minuti perché indicators.py usa candele 15m
    # Se il loop è più frequente, analizzi la stessa candela più volte (spreco)
    loop_interval_seconds: int = field(
        default_factory=lambda: int(os.getenv("LOOP_INTERVAL_SECONDS", "900"))  # 15 minuti
    )
    max_consecutive_errors: int = field(
        default_factory=lambda: int(os.getenv("MAX_CONSECUTIVE_ERRORS", "5"))
    )

    # === AI Settings ===
    # gpt-4o-mini è 15x più economico di gpt-4o (~$0.15/1M token vs $2.50/1M)
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    openai_temperature: float = field(
        default_factory=lambda: float(os.getenv("OPENAI_TEMPERATURE", "0.2"))
    )
    openai_max_tokens: int = field(
        default_factory=lambda: int(os.getenv("OPENAI_MAX_TOKENS", "500"))
    )

    # === Feature Flags ===
    enable_news: bool = field(
        default_factory=lambda: os.getenv("ENABLE_NEWS", "true").lower() == "true"
    )
    enable_sentiment: bool = field(
        default_factory=lambda: os.getenv("ENABLE_SENTIMENT", "true").lower() == "true"
    )
    enable_whale_alerts: bool = field(
        default_factory=lambda: os.getenv("ENABLE_WHALE_ALERTS", "true").lower() == "true"
    )
    enable_forecasts: bool = field(
        default_factory=lambda: os.getenv("ENABLE_FORECASTS", "true").lower() == "true"
    )
    dry_run: bool = field(
        default_factory=lambda: os.getenv("DRY_RUN", "false").lower() == "true"
    )

    # === Logging ===
    verbose: bool = field(default_factory=lambda: os.getenv("VERBOSE", "true").lower() == "true")
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    def validate(self) -> List[str]:
        """Valida la configurazione e restituisce lista di errori."""
        errors = []

        if not self.binance_api_key:
            errors.append("BINANCE_API_KEY non impostata")
        if not self.binance_api_secret:
            errors.append("BINANCE_API_SECRET non impostata")
        if not self.openai_api_key:
            errors.append("OPENAI_API_KEY non impostata")
        if not self.database_url:
            errors.append("DATABASE_URL non impostata")

        if self.loop_interval_seconds < 60:
            errors.append("LOOP_INTERVAL_SECONDS deve essere >= 60 per rispettare rate limits")

        return errors

    def is_valid(self) -> bool:
        """Controlla se la configurazione è valida."""
        return len(self.validate()) == 0


# Singleton per accesso globale
_config: TradingConfig | None = None


def get_config() -> TradingConfig:
    """Restituisce l'istanza singleton della configurazione."""
    global _config
    if _config is None:
        _config = TradingConfig()
    return _config


def reload_config() -> TradingConfig:
    """Ricarica la configurazione (utile per test)."""
    global _config
    load_dotenv(override=True)
    _config = TradingConfig()
    return _config
