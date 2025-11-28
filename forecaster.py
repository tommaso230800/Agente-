"""
Forecaster - Previsioni prezzi con Prophet.

Utilizza dati storici da Binance per generare previsioni
a breve termine (15m, 1h).

NOTA: Prophet può essere pesante in termini di RAM su Railway.
Se hai problemi, puoi disabilitare i forecasts con ENABLE_FORECASTS=false
"""

import logging
import gc
from typing import Dict, List, Tuple

import ccxt
import pandas as pd
from prophet import Prophet

logger = logging.getLogger(__name__)

# Sopprime i log verbosi di Prophet e cmdstanpy
logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
logging.getLogger("prophet").setLevel(logging.WARNING)
logging.getLogger("stan").setLevel(logging.WARNING)


class BinanceForecaster:
    """Forecaster basato su Prophet per crypto da Binance."""

    def __init__(self) -> None:
        self.exchange = ccxt.binanceusdm({
            "enableRateLimit": True,
            "options": {
                "defaultType": "future",
            },
        })
        self.last_prices: Dict[str, float] = {}

    def _fetch_candles(
        self, symbol: str, interval: str, limit: int = 200
    ) -> pd.DataFrame:
        """Recupera candele OHLCV da Binance."""
        market = f"{symbol.upper()}/USDT"
        ohlcv = self.exchange.fetch_ohlcv(market, timeframe=interval, limit=limit)
        
        if not ohlcv:
            raise RuntimeError(f"Nessun dato OHLCV per {symbol} {interval}")

        df = pd.DataFrame(
            ohlcv,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df

    def forecast(
        self, symbol: str, interval: str = "1h"
    ) -> Tuple[pd.DataFrame, float]:
        """
        Genera una previsione per il simbolo specificato.
        
        Args:
            symbol: Es. "BTC"
            interval: Timeframe dei dati storici
            
        Returns:
            (DataFrame con previsione, ultimo prezzo)
        """
        df = self._fetch_candles(symbol, interval, limit=200)

        # Prepara dati per Prophet
        df_prophet = pd.DataFrame()
        df_prophet["ds"] = df["datetime"].dt.tz_convert("UTC")
        df_prophet["y"] = df["close"]

        # Fit modello con parametri ottimizzati per velocità
        model = Prophet(
            daily_seasonality=True,
            weekly_seasonality=True,
            yearly_seasonality=False,
            changepoint_prior_scale=0.05,  # Più stabile
            seasonality_mode='additive',
        )
        model.fit(df_prophet)

        # Genera previsione
        future = model.make_future_dataframe(periods=1, freq="h")
        forecast = model.predict(future)

        last_price = float(df["close"].iloc[-1])
        self.last_prices[symbol.upper()] = last_price

        result = forecast.tail(1)[["ds", "yhat", "yhat_lower", "yhat_upper"]], last_price
        
        # Libera memoria (importante su Railway con RAM limitata)
        del model
        del df_prophet
        gc.collect()
        
        return result

    def forecast_many(
        self, tickers: List[str], intervals: Tuple[str, ...] = ("15m", "1h")
    ) -> List[Dict]:
        """
        Genera previsioni per multipli ticker e timeframe.
        
        Returns:
            Lista di dizionari con risultati previsioni
        """
        results: List[Dict] = []

        for coin in tickers:
            for interval in intervals:
                try:
                    logger.debug(f"Forecasting {coin} {interval}...")
                    fc_df, last_price = self.forecast(coin, interval="1h")
                    fc = fc_df.iloc[0]
                    forecast_price = float(fc["yhat"])
                    change_pct = (
                        (forecast_price - last_price) / last_price * 100
                        if last_price != 0
                        else 0.0
                    )

                    results.append({
                        "symbol": coin.upper(),
                        "interval": interval,
                        "last_price": last_price,
                        "forecast_price": forecast_price,
                        "change_pct": change_pct,
                        "timestamp_forecast": fc["ds"].isoformat(),
                    })
                    
                    logger.debug(
                        f"{coin} {interval}: {last_price:.2f} -> {forecast_price:.2f} "
                        f"({change_pct:+.2f}%)"
                    )
                    
                except Exception as e:
                    logger.warning(f"Errore forecast {coin} {interval}: {e}")
                    results.append({
                        "symbol": coin.upper(),
                        "interval": interval,
                        "error": str(e),
                    })

        return results


def get_crypto_forecasts(
    tickers: List[str] = None,
) -> Tuple[str, str]:
    """
    Entry point principale per ottenere previsioni.
    
    Args:
        tickers: Lista simboli (default: BTC, ETH, SOL)
        
    Returns:
        (testo_formattato, json_string)
    """
    if tickers is None:
        tickers = ["BTC", "ETH", "SOL"]

    try:
        logger.info(f"Generazione forecasts per {tickers}...")
        forecaster = BinanceForecaster()
        results = forecaster.forecast_many(tickers, intervals=("15m", "1h"))

        df = pd.DataFrame(results)
        text_summary = df.to_string(index=False)
        json_summary = df.to_json(orient="records")
        
        return text_summary, json_summary
        
    except Exception as e:
        logger.exception(f"Errore forecasting: {e}")
        return f"[ERRORE forecasting] {e}", "[]"
