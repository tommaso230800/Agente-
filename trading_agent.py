"""
Trading Agent - Decisioni AI via OpenAI.

Gestisce la comunicazione con l'API OpenAI e valida le risposte JSON.
Include retry logic per resilienza.
"""

import json
import logging
import re
import time
from typing import Any, Dict, Optional

from openai import OpenAI, APIError, APIConnectionError, RateLimitError

from config import get_config

logger = logging.getLogger(__name__)


# Schema di validazione per la risposta dell'AI
VALID_OPERATIONS = {"open", "close", "hold"}
VALID_DIRECTIONS = {"long", "short"}
VALID_SYMBOLS = {"BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX", "LINK", "DOT"}


def _extract_json_from_response(content: str) -> Optional[str]:
    """
    Estrae il JSON dalla risposta, gestendo casi come markdown code blocks.
    """
    if not content:
        return None

    # Rimuovi eventuali code blocks markdown
    content = content.strip()
    
    # Pattern per ```json ... ``` o ``` ... ```
    code_block_pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
    match = re.search(code_block_pattern, content)
    if match:
        content = match.group(1).strip()

    # Trova il primo { e l'ultimo }
    start = content.find("{")
    end = content.rfind("}")
    
    if start != -1 and end != -1 and end > start:
        return content[start : end + 1]

    return content


def _validate_trading_decision(decision: Dict[str, Any]) -> tuple[bool, str]:
    """
    Valida la decisione di trading restituita dall'AI.
    
    Returns:
        (is_valid, error_message)
    """
    operation = decision.get("operation")
    if operation not in VALID_OPERATIONS:
        return False, f"operation non valida: {operation}. Valide: {VALID_OPERATIONS}"

    if operation == "hold":
        return True, ""

    symbol = decision.get("symbol", "").upper()
    if symbol not in VALID_SYMBOLS:
        return False, f"symbol non valido: {symbol}. Validi: {VALID_SYMBOLS}"

    direction = decision.get("direction")
    if direction not in VALID_DIRECTIONS:
        return False, f"direction non valida: {direction}. Valide: {VALID_DIRECTIONS}"

    if operation == "open":
        portion = decision.get("target_portion_of_balance")
        if portion is None or not (0.0 < portion <= 1.0):
            return False, f"target_portion_of_balance non valido: {portion}. Deve essere 0.0 < x <= 1.0"

        leverage = decision.get("leverage")
        if leverage is None or not (1 <= leverage <= 20):
            return False, f"leverage non valido: {leverage}. Deve essere 1-20"

    return True, ""


def _get_fallback_decision(reason: str) -> Dict[str, Any]:
    """Restituisce una decisione di fallback sicura."""
    return {
        "operation": "hold",
        "symbol": "BTC",
        "direction": "long",
        "target_portion_of_balance": 0.0,
        "leverage": 1,
        "reason": reason,
    }


def previsione_trading_agent(prompt: str, max_retries: int = 3) -> Dict[str, Any]:
    """
    Invia il prompt al modello OpenAI e ritorna una decisione di trading validata.
    
    Args:
        prompt: Il system prompt completo con dati di mercato e portfolio
        max_retries: Numero massimo di tentativi in caso di errore
        
    Returns:
        Dizionario con la decisione di trading
    """
    config = get_config()

    if not config.openai_api_key:
        logger.error("OPENAI_API_KEY non configurata")
        return _get_fallback_decision("OpenAI API key mancante")

    client = OpenAI(api_key=config.openai_api_key)
    
    last_error = None
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Invio richiesta a OpenAI (model={config.openai_model}, attempt={attempt + 1}/{max_retries})")

            response = client.chat.completions.create(
                model=config.openai_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a strict cryptocurrency trading engine. "
                            "You MUST respond ONLY with a valid JSON object. "
                            "Do NOT include any text before or after the JSON. "
                            "Do NOT use markdown code blocks."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                temperature=config.openai_temperature,
                max_tokens=config.openai_max_tokens,
                timeout=30.0,  # 30 secondi timeout
            )

            raw_content = response.choices[0].message.content
            logger.debug(f"Risposta raw OpenAI: {raw_content[:500]}...")

            # Estrai JSON dalla risposta
            json_str = _extract_json_from_response(raw_content)
            if not json_str:
                logger.warning("Impossibile estrarre JSON dalla risposta")
                return _get_fallback_decision(f"Risposta non JSON: {raw_content[:200]}")

            # Parse JSON
            try:
                decision = json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.warning(f"JSON non valido: {e}")
                return _get_fallback_decision(f"JSON parse error: {e}")

            # Valida la decisione
            is_valid, error_msg = _validate_trading_decision(decision)
            if not is_valid:
                logger.warning(f"Decisione non valida: {error_msg}")
                return _get_fallback_decision(f"Validazione fallita: {error_msg}")

            # Normalizza i valori
            decision["symbol"] = decision.get("symbol", "BTC").upper()
            decision["operation"] = decision.get("operation", "hold").lower()
            if decision.get("direction"):
                decision["direction"] = decision["direction"].lower()

            logger.info(
                f"Decisione AI: {decision['operation']} {decision.get('symbol', 'N/A')} "
                f"{decision.get('direction', 'N/A')}"
            )

            return decision

        except RateLimitError as e:
            last_error = e
            wait_time = (2 ** attempt) * 5  # 5, 10, 20 secondi
            logger.warning(f"Rate limit OpenAI, attendo {wait_time}s... (attempt {attempt + 1})")
            time.sleep(wait_time)
            
        except APIConnectionError as e:
            last_error = e
            wait_time = (2 ** attempt) * 2  # 2, 4, 8 secondi
            logger.warning(f"Errore connessione OpenAI, attendo {wait_time}s... (attempt {attempt + 1})")
            time.sleep(wait_time)
            
        except APIError as e:
            last_error = e
            logger.warning(f"Errore API OpenAI: {e} (attempt {attempt + 1})")
            if attempt < max_retries - 1:
                time.sleep(2)
            
        except Exception as e:
            logger.exception(f"Errore inatteso in previsione_trading_agent: {e}")
            return _get_fallback_decision(f"OpenAI Error: {str(e)}")
    
    # Tutti i tentativi falliti
    logger.error(f"Tutti i {max_retries} tentativi OpenAI falliti")
    return _get_fallback_decision(f"OpenAI Error dopo {max_retries} tentativi: {str(last_error)}")
