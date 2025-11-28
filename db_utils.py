"""
Database Utilities - Logging su PostgreSQL.

Gestisce:
- Creazione schema
- Log account status
- Log operazioni bot
- Log errori
"""

from __future__ import annotations

import json
import logging
import os
import traceback
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import Json

# Import opzionale di numpy
try:
    import numpy as np
except ImportError:
    np = None

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class DBConfig:
    dsn: str


def get_db_config() -> DBConfig:
    """Recupera la configurazione del DB dalla variabile DATABASE_URL."""
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError(
            "DATABASE_URL non impostata. Imposta la variabile d'ambiente, "
            "ad esempio: postgresql://user:password@localhost:5432/trading_db"
        )
    return DBConfig(dsn=dsn)


@contextmanager
def get_connection():
    """Context manager per connessione PostgreSQL."""
    config = get_db_config()
    conn = psycopg2.connect(config.dsn)
    try:
        yield conn
    finally:
        conn.close()


# =====================
# Schema SQL
# =====================

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS account_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    balance_usd     NUMERIC(20, 8) NOT NULL,
    raw_payload     JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS open_positions (
    id                  BIGSERIAL PRIMARY KEY,
    snapshot_id         BIGINT NOT NULL REFERENCES account_snapshots(id) ON DELETE CASCADE,
    symbol              TEXT NOT NULL,
    side                TEXT NOT NULL,
    size                NUMERIC(30, 10) NOT NULL,
    entry_price         NUMERIC(30, 10),
    mark_price          NUMERIC(30, 10),
    pnl_usd             NUMERIC(30, 10),
    leverage            TEXT,
    raw_payload         JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_open_positions_snapshot_id
    ON open_positions(snapshot_id);

CREATE TABLE IF NOT EXISTS ai_contexts (
    id              BIGSERIAL PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    system_prompt   TEXT
);

CREATE TABLE IF NOT EXISTS indicators_contexts (
    id                      BIGSERIAL PRIMARY KEY,
    context_id              BIGINT NOT NULL REFERENCES ai_contexts(id) ON DELETE CASCADE,
    ticker                  TEXT NOT NULL,
    ts                      TIMESTAMPTZ,
    price                   NUMERIC(20, 8),
    ema20                   NUMERIC(20, 8),
    macd                    NUMERIC(20, 8),
    rsi_7                   NUMERIC(20, 8),
    volume_bid              NUMERIC(20, 8),
    volume_ask              NUMERIC(20, 8),
    pp                      NUMERIC(20, 8),
    s1                      NUMERIC(20, 8),
    s2                      NUMERIC(20, 8),
    r1                      NUMERIC(20, 8),
    r2                      NUMERIC(20, 8),
    open_interest_latest    NUMERIC(30, 10),
    open_interest_average   NUMERIC(30, 10),
    funding_rate            NUMERIC(20, 8),
    ema20_15m               NUMERIC(20, 8),
    ema50_15m               NUMERIC(20, 8),
    atr3_15m                NUMERIC(20, 8),
    atr14_15m               NUMERIC(20, 8),
    volume_15m_current      NUMERIC(30, 10),
    volume_15m_average      NUMERIC(30, 10),
    intraday_mid_prices     JSONB,
    intraday_ema20_series   JSONB,
    intraday_macd_series    JSONB,
    intraday_rsi7_series    JSONB,
    intraday_rsi14_series   JSONB,
    lt15m_macd_series       JSONB,
    lt15m_rsi14_series      JSONB
);

CREATE TABLE IF NOT EXISTS news_contexts (
    id              BIGSERIAL PRIMARY KEY,
    context_id      BIGINT NOT NULL REFERENCES ai_contexts(id) ON DELETE CASCADE,
    news_text       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sentiment_contexts (
    id                      BIGSERIAL PRIMARY KEY,
    context_id              BIGINT NOT NULL REFERENCES ai_contexts(id) ON DELETE CASCADE,
    value                   INTEGER,
    classification          TEXT,
    sentiment_timestamp     BIGINT,
    raw                     JSONB
);

CREATE TABLE IF NOT EXISTS forecasts_contexts (
    id                      BIGSERIAL PRIMARY KEY,
    context_id              BIGINT NOT NULL REFERENCES ai_contexts(id) ON DELETE CASCADE,
    ticker                  TEXT NOT NULL,
    timeframe               TEXT NOT NULL,
    last_price              NUMERIC(30, 10),
    prediction              NUMERIC(30, 10),
    lower_bound             NUMERIC(30, 10),
    upper_bound             NUMERIC(30, 10),
    change_pct              NUMERIC(10, 4),
    forecast_timestamp      BIGINT,
    raw                     JSONB
);

CREATE TABLE IF NOT EXISTS bot_operations (
    id                  BIGSERIAL PRIMARY KEY,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    context_id          BIGINT REFERENCES ai_contexts(id) ON DELETE CASCADE,
    operation           TEXT NOT NULL,
    symbol              TEXT,
    direction           TEXT,
    target_portion_of_balance NUMERIC(10, 4),
    leverage            NUMERIC(10, 4),
    raw_payload         JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bot_operations_created_at
    ON bot_operations(created_at);

CREATE TABLE IF NOT EXISTS errors (
    id              BIGSERIAL PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    error_type      TEXT NOT NULL,
    error_message   TEXT,
    traceback       TEXT,
    context         JSONB,
    source          TEXT
);

CREATE INDEX IF NOT EXISTS idx_errors_created_at
    ON errors(created_at);
"""


MIGRATION_SQL = """
ALTER TABLE bot_operations
    ADD COLUMN IF NOT EXISTS context_id BIGINT;

ALTER TABLE indicators_contexts
    ADD COLUMN IF NOT EXISTS ticker TEXT,
    ADD COLUMN IF NOT EXISTS ts TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS price NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS ema20 NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS macd NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS rsi_7 NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS volume_bid NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS volume_ask NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS pp NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS s1 NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS s2 NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS r1 NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS r2 NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS open_interest_latest NUMERIC(30, 10),
    ADD COLUMN IF NOT EXISTS open_interest_average NUMERIC(30, 10),
    ADD COLUMN IF NOT EXISTS funding_rate NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS ema20_15m NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS ema50_15m NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS atr3_15m NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS atr14_15m NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS volume_15m_current NUMERIC(30, 10),
    ADD COLUMN IF NOT EXISTS volume_15m_average NUMERIC(30, 10),
    ADD COLUMN IF NOT EXISTS intraday_mid_prices JSONB,
    ADD COLUMN IF NOT EXISTS intraday_ema20_series JSONB,
    ADD COLUMN IF NOT EXISTS intraday_macd_series JSONB,
    ADD COLUMN IF NOT EXISTS intraday_rsi7_series JSONB,
    ADD COLUMN IF NOT EXISTS intraday_rsi14_series JSONB,
    ADD COLUMN IF NOT EXISTS lt15m_macd_series JSONB,
    ADD COLUMN IF NOT EXISTS lt15m_rsi14_series JSONB;

ALTER TABLE sentiment_contexts
    ADD COLUMN IF NOT EXISTS value INTEGER,
    ADD COLUMN IF NOT EXISTS classification TEXT,
    ADD COLUMN IF NOT EXISTS sentiment_timestamp BIGINT,
    ADD COLUMN IF NOT EXISTS raw JSONB;

ALTER TABLE forecasts_contexts
    ADD COLUMN IF NOT EXISTS ticker TEXT,
    ADD COLUMN IF NOT EXISTS timeframe TEXT,
    ADD COLUMN IF NOT EXISTS last_price NUMERIC(30, 10),
    ADD COLUMN IF NOT EXISTS prediction NUMERIC(30, 10),
    ADD COLUMN IF NOT EXISTS lower_bound NUMERIC(30, 10),
    ADD COLUMN IF NOT EXISTS upper_bound NUMERIC(30, 10),
    ADD COLUMN IF NOT EXISTS change_pct NUMERIC(10, 4),
    ADD COLUMN IF NOT EXISTS forecast_timestamp BIGINT,
    ADD COLUMN IF NOT EXISTS raw JSONB;
"""


def init_db() -> None:
    """Crea le tabelle nel database se non esistono."""
    logger.info("Inizializzazione schema database...")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
            cur.execute(MIGRATION_SQL)
        conn.commit()

    logger.info("Schema database inizializzato")


# =====================
# Funzioni helper
# =====================


def _normalize_json_arg(value: Any) -> Any:
    """Normalizza un argomento che può essere dict/list o stringa JSON."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return {"raw": value}
    return value


def _to_plain_number(value: Any) -> Optional[float]:
    """Converte numeri (inclusi numpy scalars) in float Python."""
    if value is None:
        return None

    if np is not None:
        try:
            if isinstance(value, np.generic):
                return float(value)
        except Exception:
            pass

    if isinstance(value, (int, float)):
        return float(value)

    try:
        return float(value)
    except Exception:
        return None


def _normalize_for_json(value: Any) -> Any:
    """Converte strutture sostituendo numpy scalars con tipi Python."""
    if isinstance(value, dict):
        return {k: _normalize_for_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_for_json(v) for v in value]

    num = _to_plain_number(value)
    if num is not None:
        return num

    return value


# =====================
# Funzioni di logging
# =====================


def log_error(
    exc: BaseException,
    *,
    context: Optional[Dict[str, Any]] = None,
    source: Optional[str] = None,
) -> None:
    """
    Salva un'eccezione nella tabella `errors`.

    Args:
        exc: Eccezione catturata
        context: Dizionario opzionale con info aggiuntive
        source: Stringa per indicare la sorgente
    """
    error_type = type(exc).__name__
    error_message = str(exc)
    tb_str = traceback.format_exc()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO errors (
                    error_type,
                    error_message,
                    traceback,
                    context,
                    source
                )
                VALUES (%s, %s, %s, %s, %s);
                """,
                (
                    error_type,
                    error_message,
                    tb_str,
                    Json(context) if context is not None else None,
                    source,
                ),
            )
        conn.commit()

    logger.debug(f"Errore loggato su DB: {error_type}")


def log_account_status(account_status: Dict[str, Any]) -> int:
    """
    Logga lo stato dell'account e le posizioni aperte.

    Returns:
        ID dello snapshot creato
    """
    balance = account_status.get("balance_usd")
    if balance is None:
        raise ValueError("account_status deve contenere 'balance_usd'")

    open_positions_data = account_status.get("open_positions") or []

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO account_snapshots (balance_usd, raw_payload)
                VALUES (%s, %s)
                RETURNING id;
                """,
                (balance, Json(account_status)),
            )
            snapshot_id = cur.fetchone()[0]

            for pos in open_positions_data:
                cur.execute(
                    """
                    INSERT INTO open_positions (
                        snapshot_id, symbol, side, size,
                        entry_price, mark_price, pnl_usd,
                        leverage, raw_payload
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
                    """,
                    (
                        snapshot_id,
                        pos.get("symbol"),
                        pos.get("side"),
                        pos.get("size"),
                        pos.get("entry_price"),
                        pos.get("mark_price"),
                        pos.get("pnl_usd"),
                        pos.get("leverage"),
                        Json(pos),
                    ),
                )

        conn.commit()

    logger.debug(f"Account snapshot salvato (id={snapshot_id})")
    return snapshot_id


def log_bot_operation(
    operation_payload: Dict[str, Any],
    *,
    system_prompt: Optional[str] = None,
    indicators: Optional[Any] = None,
    news_text: Optional[str] = None,
    sentiment: Optional[Any] = None,
    forecasts: Optional[Any] = None,
) -> int:
    """
    Logga un'operazione del bot e tutti gli input associati.

    Returns:
        ID dell'operazione creata
    """
    operation = operation_payload.get("operation")
    if operation is None:
        raise ValueError("operation_payload deve contenere 'operation'")

    symbol = operation_payload.get("symbol")
    direction = operation_payload.get("direction")
    target_portion_of_balance = operation_payload.get("target_portion_of_balance")
    leverage = operation_payload.get("leverage")

    sentiment_norm = _normalize_json_arg(sentiment) if sentiment is not None else None
    forecasts_norm = _normalize_json_arg(forecasts) if forecasts is not None else None

    with get_connection() as conn:
        with conn.cursor() as cur:
            # 1) Crea il contesto generale
            cur.execute(
                """
                INSERT INTO ai_contexts (system_prompt)
                VALUES (%s)
                RETURNING id;
                """,
                (system_prompt,),
            )
            context_id = cur.fetchone()[0]

            # 2) Indicatori
            if indicators is not None:
                for indicator in indicators:
                    indicators_norm = (
                        _normalize_json_arg(indicator)
                        if indicator is not None
                        else None
                    )

                    if indicators_norm is not None:
                        indicator_items: List[Dict[str, Any]] = []

                        if isinstance(indicators_norm, dict):
                            if "ticker" in indicators_norm:
                                indicator_items = [indicators_norm]
                            else:
                                for tkr, data in indicators_norm.items():
                                    if isinstance(data, dict):
                                        item = {"ticker": tkr}
                                        item.update(data)
                                        indicator_items.append(item)
                        elif isinstance(indicators_norm, list):
                            indicator_items = [
                                x for x in indicators_norm if isinstance(x, dict)
                            ]

                        for item in indicator_items:
                            ticker = item.get("ticker") or item.get("symbol")
                            if not ticker:
                                continue

                            ts = None
                            ts_raw = item.get("timestamp")
                            if isinstance(ts_raw, str):
                                try:
                                    ts = datetime.fromisoformat(ts_raw)
                                except Exception:
                                    ts = None

                            cur.execute(
                                """
                                INSERT INTO indicators_contexts (
                                    context_id, ticker, ts, price, ema20, macd, rsi_7
                                )
                                VALUES (%s, %s, %s, %s, %s, %s, %s);
                                """,
                                (
                                    context_id,
                                    ticker,
                                    ts,
                                    _to_plain_number(item.get("current_price")),
                                    _to_plain_number(item.get("current_ema20")),
                                    _to_plain_number(item.get("current_macd")),
                                    _to_plain_number(item.get("current_rsi7")),
                                ),
                            )

            # 3) News
            if news_text:
                cur.execute(
                    """
                    INSERT INTO news_contexts (context_id, news_text)
                    VALUES (%s, %s);
                    """,
                    (context_id, news_text),
                )

            # 4) Sentiment
            if sentiment_norm is not None:
                value = sentiment_norm.get("valore")
                classification = sentiment_norm.get("classificazione")
                ts_raw = sentiment_norm.get("timestamp")
                try:
                    ts_val = int(ts_raw) if ts_raw is not None else None
                except Exception:
                    ts_val = None

                cur.execute(
                    """
                    INSERT INTO sentiment_contexts (
                        context_id, value, classification,
                        sentiment_timestamp, raw
                    )
                    VALUES (%s, %s, %s, %s, %s);
                    """,
                    (
                        context_id,
                        value,
                        classification,
                        ts_val,
                        Json(sentiment_norm),
                    ),
                )

            # 5) Forecasts
            if forecasts_norm is not None:
                forecast_items: List[Dict[str, Any]] = []
                if isinstance(forecasts_norm, list):
                    forecast_items = [
                        x for x in forecasts_norm if isinstance(x, dict)
                    ]
                elif isinstance(forecasts_norm, dict):
                    forecast_items = [forecasts_norm]

                for f in forecast_items:
                    ticker = f.get("symbol") or f.get("ticker")
                    timeframe = f.get("interval") or f.get("timeframe")

                    if not ticker or not timeframe:
                        continue

                    cur.execute(
                        """
                        INSERT INTO forecasts_contexts (
                            context_id, ticker, timeframe,
                            last_price, prediction, change_pct, raw
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s);
                        """,
                        (
                            context_id,
                            ticker,
                            timeframe,
                            _to_plain_number(f.get("last_price")),
                            _to_plain_number(f.get("forecast_price")),
                            _to_plain_number(f.get("change_pct")),
                            Json(_normalize_for_json(f)),
                        ),
                    )

            # 6) Operazione del bot
            cur.execute(
                """
                INSERT INTO bot_operations (
                    context_id, operation, symbol, direction,
                    target_portion_of_balance, leverage, raw_payload
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
                """,
                (
                    context_id,
                    operation,
                    symbol,
                    direction,
                    target_portion_of_balance,
                    leverage,
                    Json(operation_payload),
                ),
            )
            op_id = cur.fetchone()[0]

        conn.commit()

    logger.debug(f"Operazione bot salvata (id={op_id}, context={context_id})")
    return op_id


# =====================
# Funzioni di lettura
# =====================


def get_latest_account_snapshot() -> Optional[Dict[str, Any]]:
    """Restituisce l'ultimo snapshot dell'account."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT raw_payload
                FROM account_snapshots
                ORDER BY created_at DESC
                LIMIT 1;
                """
            )
            row = cur.fetchone()
            if not row:
                return None
            return row[0]


def get_recent_bot_operations(limit: int = 50) -> List[Dict[str, Any]]:
    """Restituisce le ultime N operazioni del bot."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT raw_payload
                FROM bot_operations
                ORDER BY created_at DESC
                LIMIT %s;
                """,
                (limit,),
            )
            rows = cur.fetchall()
            return [r[0] for r in rows]


if __name__ == "__main__":
    init_db()
    print("Database inizializzato con successo")
