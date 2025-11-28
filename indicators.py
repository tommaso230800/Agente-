"""
Indicatori Tecnici - Calcolo indicatori via ccxt e ta library.

Supporta:
- EMA (20)
- MACD
- RSI (7, 14)
- ATR (14)
- Volume analysis
"""

import logging
from typing import Dict, List, Tuple

import ccxt
import pandas as pd
import ta

logger = logging.getLogger(__name__)

SUPPORTED_INTERVALS = {"1m", "5m", "15m", "1h", "4h", "1d"}


def _get_exchange() -> ccxt.binanceusdm:
    """Restituisce un'istanza dell'exchange Binance Futures."""
    exchange = ccxt.binanceusdm({
        "enableRateLimit": True,
        "options": {
            "defaultType": "future",
        },
    })
    return exchange


def _fetch_ohlcv(symbol: str, interval: str = "15m", limit: int = 200) -> pd.DataFrame:
    """
    Recupera i dati OHLCV da Binance Futures.
    
    Args:
        symbol: Es. "BTC"
        interval: Timeframe (1m, 5m, 15m, 1h, 4h, 1d)
        limit: Numero di candele
        
    Returns:
        DataFrame con colonne: timestamp, open, high, low, close, volume, datetime
    """
    if interval not in SUPPORTED_INTERVALS:
        raise ValueError(f"Interval '{interval}' non supportato: {SUPPORTED_INTERVALS}")

    exchange = _get_exchange()
    market = f"{symbol.upper()}/USDT"

    logger.debug(f"Fetch OHLCV: {market} {interval} limit={limit}")
    
    ohlcv = exchange.fetch_ohlcv(market, timeframe=interval, limit=limit)
    if not ohlcv:
        raise RuntimeError(f"Nessun dato OHLCV per {symbol} {interval}")

    df = pd.DataFrame(
        ohlcv,
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    
    return df


def _compute_indicators_from_df(df: pd.DataFrame) -> Dict:
    """
    Calcola tutti gli indicatori tecnici da un DataFrame OHLCV.
    
    Returns:
        Dizionario con tutti gli indicatori calcolati
    """
    if df.empty:
        raise ValueError("DataFrame vuoto in _compute_indicators_from_df")

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # Calcolo indicatori
    ema20 = ta.trend.EMAIndicator(close=close, window=20).ema_indicator()
    macd = ta.trend.MACD(close=close).macd()
    rsi14 = ta.momentum.RSIIndicator(close=close, window=14).rsi()
    rsi7 = ta.momentum.RSIIndicator(close=close, window=7).rsi()
    atr14 = ta.volatility.AverageTrueRange(
        high=high, low=low, close=close, window=14
    ).average_true_range()

    last_row = df.iloc[-1]

    return {
        "timestamp": last_row["datetime"].isoformat(),
        "current_price": float(last_row["close"]),
        "current_ema20": float(ema20.iloc[-1]),
        "current_macd": float(macd.iloc[-1]),
        "current_rsi14": float(rsi14.iloc[-1]),
        "current_rsi7": float(rsi7.iloc[-1]),
        "atr14": float(atr14.iloc[-1]),
        "volume_current": float(last_row["volume"]),
        "volume_average": float(volume.tail(20).mean()),
    }


def analyze_ticker(symbol: str, interval: str = "15m") -> Dict:
    """
    Analizza un singolo ticker e restituisce gli indicatori.
    
    Args:
        symbol: Es. "BTC", "ETH"
        interval: Timeframe
        
    Returns:
        Dizionario con indicatori e metadati
    """
    df = _fetch_ohlcv(symbol, interval=interval, limit=200)
    indicators = _compute_indicators_from_df(df)
    indicators["symbol"] = symbol.upper()
    indicators["interval"] = interval
    
    logger.debug(
        f"{symbol}: price={indicators['current_price']:.2f}, "
        f"rsi14={indicators['current_rsi14']:.1f}, "
        f"macd={indicators['current_macd']:.4f}"
    )
    
    return indicators


def format_output(data: Dict) -> str:
    """Formatta l'output degli indicatori in testo leggibile."""
    lines = [
        f"=== {data['symbol']} ({data['interval']}) ===",
        f"Timestamp (UTC): {data['timestamp']}",
        f"Prezzo attuale: {data['current_price']:.4f} USDT",
        f"EMA20: {data['current_ema20']:.4f}",
        f"MACD: {data['current_macd']:.4f}",
        f"RSI(14): {data['current_rsi14']:.2f}",
        f"RSI(7): {data['current_rsi7']:.2f}",
        f"ATR(14): {data['atr14']:.4f}",
        f"Volume (candela corrente): {data['volume_current']:.4f}",
        f"Volume medio (ultime 20): {data['volume_average']:.4f}",
    ]
    return "\n".join(lines) + "\n"


def analyze_multiple_tickers(
    tickers: List[str],
    interval: str = "15m",
) -> Tuple[str, List[Dict]]:
    """
    Analizza multipli ticker e restituisce output formattato.
    
    Args:
        tickers: Lista di simboli (es. ["BTC", "ETH", "SOL"])
        interval: Timeframe
        
    Returns:
        (testo_formattato, lista_dizionari_dati)
    """
    full_output = ""
    datas: List[Dict] = []

    for ticker in tickers:
        try:
            logger.info(f"Analisi {ticker}...")
            data = analyze_ticker(ticker, interval=interval)
            datas.append(data)
            full_output += format_output(data)
        except Exception as e:
            logger.warning(f"Errore analisi {ticker}: {e}")
            full_output += f"\n[ERRORE] Analisi {ticker}: {e}\n"

    return full_output, datas
