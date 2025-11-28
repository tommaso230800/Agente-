"""
Sentiment Analysis - Fear & Greed Index da CoinMarketCap.

Recupera l'indice di sentiment del mercato crypto.
"""

import logging
import os
from typing import Any, Dict, Optional, Tuple, Union

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

API_URL = "https://pro-api.coinmarketcap.com/v3/fear-and-greed/historical"
REQUEST_TIMEOUT = 15  # secondi - aumentato per API lente


def get_latest_fear_and_greed() -> Optional[Dict[str, Any]]:
    """
    Recupera l'ultimo valore del Fear & Greed Index.
    
    Returns:
        Dizionario con valore, classificazione e timestamp,
        oppure None se errore
    """
    api_key = os.getenv("CMC_PRO_API_KEY")
    
    if not api_key:
        logger.warning("CMC_PRO_API_KEY non impostata, sentiment non disponibile")
        return None

    headers = {
        "Accepts": "application/json",
        "X-CMC_PRO_API_KEY": api_key,
    }

    parameters = {
        "limit": 1,
    }

    try:
        response = requests.get(
            API_URL,
            headers=headers,
            params=parameters,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()

        data = response.json()

        if data and "data" in data and len(data["data"]) > 0:
            latest_record = data["data"][0]
            
            result = {
                "valore": latest_record.get("value"),
                "classificazione": latest_record.get("value_classification"),
                "timestamp": latest_record.get("timestamp"),
            }
            
            logger.info(
                f"Fear & Greed: {result['valore']} ({result['classificazione']})"
            )
            
            return result
        else:
            logger.warning("Risposta API senza dati validi")
            return None

    except requests.exceptions.HTTPError as e:
        logger.warning(f"Errore HTTP CoinMarketCap: {e}")
    except requests.exceptions.ConnectionError as e:
        logger.warning(f"Errore connessione CoinMarketCap: {e}")
    except requests.exceptions.Timeout as e:
        logger.warning(f"Timeout CoinMarketCap: {e}")
    except requests.exceptions.RequestException as e:
        logger.warning(f"Errore richiesta CoinMarketCap: {e}")
    except Exception as e:
        logger.warning(f"Errore generico sentiment: {e}")

    return None


def get_sentiment() -> Union[Tuple[str, Dict[str, Any]], str]:
    """
    Restituisce il sentiment formattato.
    
    Returns:
        Tupla (testo_formattato, dizionario_dati) se successo,
        stringa errore altrimenti
    """
    sentiment_data = get_latest_fear_and_greed()
    
    if sentiment_data:
        text = (
            f"Sentiment del mercato (Fear & Greed Index):\n"
            f"  Valore: {sentiment_data['valore']}\n"
            f"  Classificazione: {sentiment_data['classificazione']}\n"
            f"  Timestamp: {sentiment_data['timestamp']}"
        )
        return text, sentiment_data
    else:
        return "Impossibile recuperare il sentiment del mercato."
