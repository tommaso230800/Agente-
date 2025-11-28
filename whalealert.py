"""
Whale Alert - Traccia grandi movimenti crypto.

Fonte: whale-alert.io
"""

import logging
from datetime import datetime
from typing import Optional

import requests

logger = logging.getLogger(__name__)

WHALE_ALERT_URL = (
    "https://whale-alert.io/data.json?"
    "alerts=9&prices=BTC&hodl=bitcoin%2CBTC"
    "&potential_profit=bitcoin%2CBTC"
    "&average_buy_price=bitcoin%2CBTC"
    "&realized_profit=bitcoin%2CBTC"
    "&volume=bitcoin%2CBTC&news=true"
)
REQUEST_TIMEOUT = 15  # secondi


def get_whale_alerts() -> Optional[str]:
    """
    Recupera e stampa whale alerts.
    
    Returns:
        Stringa formattata con alerts o None se errore
    """
    try:
        response = requests.get(WHALE_ALERT_URL, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        data = response.json()
        alerts = data.get("alerts", [])

        if not alerts:
            logger.info("Nessun whale alert trovato")
            return None

        output_lines = ["🐋 WHALE ALERTS - MOVIMENTI CRYPTO SIGNIFICATIVI 🐋", "=" * 80]

        for alert in alerts:
            parts = alert.split(",", 5)

            if len(parts) >= 6:
                timestamp = parts[0]
                emoji = parts[1]
                amount = parts[2].strip('"')
                usd_value = parts[3].strip('"')
                description = parts[4].strip('"')
                link = parts[5]

                try:
                    dt = datetime.fromtimestamp(int(timestamp))
                    formatted_time = dt.strftime("%d/%m/%Y %H:%M:%S")
                except Exception:
                    formatted_time = "N/A"

                output_lines.extend([
                    f"\n{emoji} ALERT del {formatted_time}",
                    f"💰 Importo: {amount}",
                    f"💵 Valore USD: {usd_value}",
                    f"📝 Descrizione: {description}",
                    f"🔗 Link: {link}",
                    "-" * 80,
                ])

        result = "\n".join(output_lines)
        logger.debug(result)
        return result

    except requests.exceptions.RequestException as e:
        logger.warning(f"Errore richiesta whale alert: {e}")
        return None
    except Exception as e:
        logger.warning(f"Errore whale alert: {e}")
        return None


def format_whale_alerts_to_string() -> str:
    """
    Versione che restituisce una stringa formattata.
    
    Returns:
        Stringa con whale alerts formattati
    """
    try:
        response = requests.get(WHALE_ALERT_URL, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()

        alerts = data.get("alerts", [])

        if not alerts:
            logger.debug("Nessun whale alert disponibile")
            return "Nessun alert trovato."

        result = "🐋 WHALE ALERTS - MOVIMENTI CRYPTO SIGNIFICATIVI 🐋\n\n"

        for alert in alerts:
            parts = alert.split(",", 5)

            if len(parts) >= 6:
                timestamp = parts[0]
                emoji = parts[1]
                amount = parts[2].strip('"')
                usd_value = parts[3].strip('"')
                description = parts[4].strip('"')

                try:
                    dt = datetime.fromtimestamp(int(timestamp))
                    formatted_time = dt.strftime("%d/%m/%Y %H:%M:%S")
                except Exception:
                    formatted_time = "N/A"

                result += f"{emoji} ALERT del {formatted_time}\n"
                result += f"Importo: {amount}\n"
                result += f"Valore USD: {usd_value}\n"
                result += f"Descrizione: {description}\n\n"

        alerts_count = len(alerts)
        logger.info(f"Recuperati {alerts_count} whale alerts")
        
        return result

    except Exception as e:
        logger.warning(f"Errore whale alerts: {e}")
        return f"Errore: {e}"


if __name__ == "__main__":
    get_whale_alerts()
