"""
Main entry point per il Trading Agent.

Esegue un loop continuo che:
1. Raccoglie dati di mercato (indicatori, news, sentiment, whale alerts, forecasts)
2. Costruisce il prompt per l'AI
3. Ottiene una decisione di trading
4. Esegue l'ordine su Binance Futures
5. Logga tutto su PostgreSQL
6. Attende l'intervallo configurato e ripete

Supporta:
- Graceful shutdown (SIGTERM/SIGINT)
- Dry run mode
- Configurazione via environment variables
- Deploy su Railway
"""

import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config import get_config, TradingConfig
import db_utils

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


# Flag globale per graceful shutdown
shutdown_requested = False


def signal_handler(signum, frame):
    """Handler per SIGTERM e SIGINT."""
    global shutdown_requested
    sig_name = signal.Signals(signum).name
    logger.info(f"Ricevuto segnale {sig_name}, avvio shutdown...")
    shutdown_requested = True


# Registra handlers per graceful shutdown
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


def load_modules():
    """
    Import dinamico dei moduli per gestire errori di import gracefully.
    """
    modules = {}

    try:
        from indicators import analyze_multiple_tickers
        modules["analyze_multiple_tickers"] = analyze_multiple_tickers
    except ImportError as e:
        logger.warning(f"Impossibile importare indicators: {e}")
        modules["analyze_multiple_tickers"] = None

    try:
        from news_feed import fetch_latest_news
        modules["fetch_latest_news"] = fetch_latest_news
    except ImportError as e:
        logger.warning(f"Impossibile importare news_feed: {e}")
        modules["fetch_latest_news"] = None

    try:
        from sentiment import get_sentiment
        modules["get_sentiment"] = get_sentiment
    except ImportError as e:
        logger.warning(f"Impossibile importare sentiment: {e}")
        modules["get_sentiment"] = None

    try:
        from forecaster import get_crypto_forecasts
        modules["get_crypto_forecasts"] = get_crypto_forecasts
    except ImportError as e:
        logger.warning(f"Impossibile importare forecaster: {e}")
        modules["get_crypto_forecasts"] = None

    try:
        from whalealert import format_whale_alerts_to_string
        modules["format_whale_alerts_to_string"] = format_whale_alerts_to_string
    except ImportError as e:
        logger.warning(f"Impossibile importare whalealert: {e}")
        modules["format_whale_alerts_to_string"] = None

    try:
        from trading_agent import previsione_trading_agent
        modules["previsione_trading_agent"] = previsione_trading_agent
    except ImportError as e:
        logger.error(f"Impossibile importare trading_agent: {e}")
        modules["previsione_trading_agent"] = None

    try:
        from binance_trader import BinanceFuturesTrader
        modules["BinanceFuturesTrader"] = BinanceFuturesTrader
    except ImportError as e:
        logger.error(f"Impossibile importare binance_trader: {e}")
        modules["BinanceFuturesTrader"] = None

    return modules


def build_system_prompt(
    account_status: Dict[str, Any],
    context_info: str,
    config: TradingConfig,
) -> str:
    """Costruisce il system prompt completo."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(base_dir, "system_prompt.txt")

    try:
        with open(template_path, "r", encoding="utf-8") as f:
            template = f.read()
    except FileNotFoundError:
        logger.warning(f"Template non trovato: {template_path}, uso template di base")
        template = (
            "You are a crypto trading AI.\n\n"
            "Portfolio: {}\n\n"
            "Context: {}\n\n"
            "Respond with JSON: operation, symbol, direction, target_portion_of_balance, leverage, reason"
        )

    return template.format(json.dumps(account_status, indent=2), context_info)


def gather_market_data(
    modules: Dict,
    config: TradingConfig,
) -> tuple[str, Dict[str, Any]]:
    """
    Raccoglie tutti i dati di mercato disponibili.
    Ogni sorgente è indipendente: se una fallisce, le altre continuano.
    
    Returns:
        (context_string, raw_data_dict)
    """
    sections = []
    raw_data = {
        "indicators": None,
        "news": None,
        "sentiment": None,
        "forecasts": None,
        "whale_alerts": None,
    }

    # === Indicatori Tecnici (PRIORITÀ ALTA) ===
    if modules.get("analyze_multiple_tickers"):
        try:
            logger.info(f"Recupero indicatori per {config.tickers}...")
            indicators_txt, indicators_json = modules["analyze_multiple_tickers"](
                config.tickers, interval="15m"
            )
            if indicators_txt:
                sections.append(f"=== INDICATORI TECNICI (Binance Futures, 15m) ===\n{indicators_txt}")
                raw_data["indicators"] = indicators_json
                logger.info("✓ Indicatori recuperati")
        except Exception as e:
            logger.warning(f"✗ Errore recupero indicatori: {e}")

    # === Forecasts (OPZIONALE - può essere pesante) ===
    if config.enable_forecasts and modules.get("get_crypto_forecasts"):
        try:
            logger.info("Recupero previsioni Prophet...")
            forecasts_txt, forecasts_json = modules["get_crypto_forecasts"](config.tickers)
            if forecasts_txt and "[ERRORE" not in forecasts_txt:
                sections.append(f"=== PREVISIONI PREZZO (Prophet) ===\n{forecasts_txt}")
                raw_data["forecasts"] = forecasts_json
                logger.info("✓ Forecasts recuperati")
            else:
                logger.warning("✗ Forecasts non disponibili")
        except Exception as e:
            logger.warning(f"✗ Errore recupero forecasts: {e}")

    # === News (OPZIONALE) ===
    if config.enable_news and modules.get("fetch_latest_news"):
        try:
            logger.info("Recupero news...")
            news_txt = modules["fetch_latest_news"](max_chars=2000)
            if news_txt and "Failed" not in news_txt:
                sections.append(f"=== NEWS CRYPTO ===\n{news_txt}")
                raw_data["news"] = news_txt
                logger.info("✓ News recuperate")
            else:
                logger.warning("✗ News non disponibili")
        except Exception as e:
            logger.warning(f"✗ Errore recupero news: {e}")

    # === Sentiment (OPZIONALE - richiede CMC_PRO_API_KEY) ===
    if config.enable_sentiment and modules.get("get_sentiment"):
        try:
            logger.info("Recupero sentiment Fear & Greed...")
            sentiment_result = modules["get_sentiment"]()
            if isinstance(sentiment_result, tuple):
                sentiment_txt, sentiment_json = sentiment_result
            else:
                sentiment_txt = str(sentiment_result)
                sentiment_json = None

            if sentiment_txt and "Impossibile" not in sentiment_txt:
                sections.append(f"=== SENTIMENT (Fear & Greed Index) ===\n{sentiment_txt}")
                raw_data["sentiment"] = sentiment_json
                logger.info("✓ Sentiment recuperato")
            else:
                logger.info("Sentiment non disponibile (CMC_PRO_API_KEY mancante?)")
        except Exception as e:
            logger.warning(f"✗ Errore recupero sentiment: {e}")

    # === Whale Alerts (OPZIONALE) ===
    if config.enable_whale_alerts and modules.get("format_whale_alerts_to_string"):
        try:
            logger.info("Recupero whale alerts...")
            whale_txt = modules["format_whale_alerts_to_string"]()
            if whale_txt and "Errore" not in whale_txt and "Nessun alert" not in whale_txt:
                sections.append(f"=== WHALE ALERTS ===\n{whale_txt}")
                raw_data["whale_alerts"] = whale_txt
                logger.info("✓ Whale alerts recuperati")
            else:
                logger.debug("Nessun whale alert significativo")
        except Exception as e:
            logger.warning(f"✗ Errore recupero whale alerts: {e}")

    # Riepilogo
    data_sources = sum(1 for v in raw_data.values() if v is not None)
    logger.info(f"Dati mercato: {data_sources}/5 sorgenti disponibili")
    
    context_info = "\n\n".join(sections) if sections else "Dati di mercato limitati. Procedi con cautela."

    return context_info, raw_data


def get_fresh_prices(tickers: List[str]) -> Dict[str, float]:
    """
    Recupera prezzi freschi immediatamente prima della decisione AI.
    Risolve il problema del "latency gap" segnalato.
    """
    prices = {}
    try:
        import ccxt
        exchange = ccxt.binanceusdm({"enableRateLimit": True})
        
        for ticker in tickers:
            try:
                symbol = f"{ticker.upper()}/USDT"
                ticker_data = exchange.fetch_ticker(symbol)
                prices[ticker.upper()] = float(ticker_data["last"])
            except Exception as e:
                logger.warning(f"Errore prezzo {ticker}: {e}")
    except Exception as e:
        logger.warning(f"Errore fetch prezzi freschi: {e}")
    
    return prices


def run_trading_cycle(
    bot,
    modules: Dict,
    config: TradingConfig,
) -> Optional[Dict[str, Any]]:
    """
    Esegue un singolo ciclo di trading.
    
    Returns:
        Risultato dell'esecuzione o None se errore
    """
    cycle_start = datetime.now(timezone.utc)
    logger.info(f"=== Inizio ciclo trading @ {cycle_start.isoformat()} ===")

    # 1. Stato account
    try:
        account_status = bot.get_account_status_dict()
        logger.info(
            f"Balance: ${account_status.get('balance_usd', 0):.2f} "
            f"(free: ${account_status.get('free_balance_usd', 0):.2f})"
        )
        if account_status.get("open_positions"):
            logger.info(f"Posizioni aperte: {len(account_status['open_positions'])}")
    except Exception as e:
        logger.error(f"Errore recupero stato account: {e}")
        raise

    # 2. Dati di mercato
    context_info, raw_data = gather_market_data(modules, config)

    # 2b. Prezzi FRESCHI (risolve latency gap)
    fresh_prices = get_fresh_prices(config.tickers)
    if fresh_prices:
        price_lines = [f"  {k}: ${v:,.2f}" for k, v in fresh_prices.items()]
        fresh_price_section = "=== PREZZI REAL-TIME (aggiornati ora) ===\n" + "\n".join(price_lines)
        context_info = fresh_price_section + "\n\n" + context_info
        logger.info(f"Prezzi freschi: {fresh_prices}")

    # 3. Costruisci prompt
    system_prompt = build_system_prompt(account_status, context_info, config)

    if config.verbose:
        logger.debug(f"System prompt ({len(system_prompt)} chars)")

    # 4. Decisione AI
    if not modules.get("previsione_trading_agent"):
        logger.error("Modulo trading_agent non disponibile")
        return None

    logger.info("Richiesta decisione all'AI...")
    decision = modules["previsione_trading_agent"](system_prompt)

    logger.info(
        f"Decisione: {decision.get('operation')} {decision.get('symbol', '')} "
        f"{decision.get('direction', '')} - {decision.get('reason', '')[:100]}"
    )

    # 5. Esecuzione ordine
    order_result = {"status": "skipped", "reason": "dry_run mode"}

    if config.dry_run:
        logger.info("[DRY RUN] Ordine non eseguito")
    else:
        logger.info("Esecuzione ordine...")
        order_result = bot.execute_signal(decision)
        logger.info(f"Risultato: {order_result.get('status', 'unknown')}")

    # 6. Logging su DB
    try:
        # Prepara forecasts per DB
        forecasts_for_db = raw_data.get("forecasts")
        if isinstance(forecasts_for_db, str):
            try:
                forecasts_for_db = json.loads(forecasts_for_db)
            except (json.JSONDecodeError, TypeError):
                pass

        op_id = db_utils.log_bot_operation(
            decision,
            system_prompt=system_prompt,
            indicators=raw_data.get("indicators"),
            news_text=raw_data.get("news"),
            sentiment=raw_data.get("sentiment"),
            forecasts=forecasts_for_db,
        )
        logger.info(f"Operazione salvata su DB (id={op_id})")
    except Exception as e:
        logger.warning(f"Errore salvataggio su DB: {e}")

    cycle_end = datetime.now(timezone.utc)
    duration = (cycle_end - cycle_start).total_seconds()
    logger.info(f"=== Ciclo completato in {duration:.1f}s ===")

    return {
        "decision": decision,
        "order_result": order_result,
        "duration_seconds": duration,
    }


def main() -> None:
    """Entry point principale con loop continuo."""
    global shutdown_requested

    logger.info("=" * 60)
    logger.info("BINANCE TRADING AGENT - Avvio")
    logger.info("=" * 60)

    # Carica configurazione
    config = get_config()

    # Valida configurazione
    validation_errors = config.validate()
    if validation_errors:
        for err in validation_errors:
            logger.error(f"Config error: {err}")
        sys.exit(1)

    logger.info(f"Mode: {'TESTNET' if config.testnet else 'MAINNET'}")
    logger.info(f"Tickers: {config.tickers}")
    logger.info(f"Loop interval: {config.loop_interval_seconds}s")
    logger.info(f"Dry run: {config.dry_run}")
    logger.info(f"AI model: {config.openai_model}")

    # Inizializza database
    try:
        logger.info("Inizializzazione database...")
        db_utils.init_db()
        logger.info("Database inizializzato")
    except Exception as e:
        logger.error(f"Errore inizializzazione DB: {e}")
        sys.exit(1)

    # Carica moduli
    modules = load_modules()

    if not modules.get("BinanceFuturesTrader"):
        logger.error("Modulo BinanceFuturesTrader non disponibile, impossibile continuare")
        sys.exit(1)

    # Inizializza trader
    try:
        bot = modules["BinanceFuturesTrader"](
            api_key=config.binance_api_key,
            api_secret=config.binance_api_secret,
            testnet=config.testnet,
        )
        logger.info(f"Trader inizializzato ({'testnet' if config.testnet else 'mainnet'})")
    except Exception as e:
        logger.error(f"Errore inizializzazione trader: {e}")
        sys.exit(1)

    # Contatore errori consecutivi
    consecutive_errors = 0

    # === LOOP PRINCIPALE ===
    logger.info("Avvio loop principale...")

    while not shutdown_requested:
        try:
            result = run_trading_cycle(bot, modules, config)

            if result:
                consecutive_errors = 0
            else:
                consecutive_errors += 1

        except Exception as e:
            consecutive_errors += 1
            logger.exception(f"Errore nel ciclo di trading: {e}")

            # Log errore su DB
            try:
                db_utils.log_error(
                    e,
                    context={"consecutive_errors": consecutive_errors},
                    source="main_loop",
                )
            except Exception:
                pass

        # Controlla limite errori consecutivi
        if consecutive_errors >= config.max_consecutive_errors:
            logger.error(
                f"Raggiunti {consecutive_errors} errori consecutivi, "
                f"attendo {config.loop_interval_seconds * 2}s prima di riprovare"
            )
            time.sleep(config.loop_interval_seconds * 2)
            consecutive_errors = 0

        # Attendi prossimo ciclo (con check shutdown ogni secondo)
        if not shutdown_requested:
            logger.info(f"Prossimo ciclo tra {config.loop_interval_seconds}s...")
            for _ in range(config.loop_interval_seconds):
                if shutdown_requested:
                    break
                time.sleep(1)

    logger.info("Shutdown completato.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception(f"Errore fatale: {e}")
        try:
            db_utils.log_error(
                e,
                context={"phase": "startup"},
                source="main",
            )
        except Exception:
            pass
        sys.exit(1)
