"""
Binance Futures Trader - Wrapper ccxt per operazioni su Binance Futures USD-M.

Gestisce:
- Apertura/chiusura posizioni
- Gestione leva
- STOP-LOSS e TAKE-PROFIT automatici
- Query stato account
"""

import logging
from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict, List, Optional

import ccxt

logger = logging.getLogger(__name__)

# === RISK MANAGEMENT SETTINGS ===
# Stop Loss e Take Profit come percentuali dal prezzo di entrata
DEFAULT_STOP_LOSS_PCT = 0.02      # 2% stop loss
DEFAULT_TAKE_PROFIT_PCT = 0.04   # 4% take profit (ratio 1:2)
MAX_LEVERAGE = 5                  # Leva massima consentita (override AI)


class BinanceFuturesTrader:
    """
    Wrapper per operare su Binance Futures (USD-M) tramite ccxt.
    
    Compatibile con l'output JSON dell'agente AI:
    {
        "operation": "open",
        "symbol": "BTC",
        "direction": "long",
        "target_portion_of_balance": 0.3,
        "leverage": 3,
        "reason": "..."
    }
    """

    def __init__(self, api_key: str, api_secret: str, testnet: bool = True) -> None:
        self.testnet = testnet

        # USDT-M futures
        self.exchange = ccxt.binanceusdm({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": {
                "defaultType": "future",
            },
        })

        if testnet:
            try:
                self.exchange.set_sandbox_mode(True)
                logger.info("Binance Futures Testnet mode attivato")
            except Exception as e:
                logger.warning(f"Impossibile attivare sandbox mode: {e}")

    def _market_symbol(self, symbol: str) -> str:
        """Converte symbol in formato market ccxt."""
        symbol = symbol.upper()
        if "/" in symbol:
            return symbol
        return f"{symbol}/USDT"

    def _get_free_usdt_balance(self) -> float:
        """Restituisce il balance USDT disponibile."""
        balance = self.exchange.fetch_balance()
        free = balance.get("USDT", {}).get("free", 0.0)
        return float(free)

    def _get_current_price(self, market: str) -> float:
        """Restituisce il prezzo corrente del market."""
        ticker = self.exchange.fetch_ticker(market)
        return float(ticker["last"])

    def _round_price(self, price: float, market: str) -> float:
        """Arrotonda il prezzo secondo le regole del market."""
        # Per semplicità, arrotondiamo a 2 decimali per la maggior parte delle crypto
        # In produzione, dovresti usare exchange.market(market)['precision']['price']
        try:
            market_info = self.exchange.market(market)
            precision = market_info.get('precision', {}).get('price', 2)
            return float(Decimal(str(price)).quantize(Decimal(10) ** -precision, rounding=ROUND_DOWN))
        except Exception:
            return round(price, 2)

    def _round_quantity(self, qty: float, market: str) -> float:
        """Arrotonda la quantità secondo le regole del market."""
        try:
            market_info = self.exchange.market(market)
            precision = market_info.get('precision', {}).get('amount', 6)
            return float(Decimal(str(qty)).quantize(Decimal(10) ** -precision, rounding=ROUND_DOWN))
        except Exception:
            return round(qty, 6)

    def _place_stop_loss(
        self,
        market: str,
        side: str,
        quantity: float,
        stop_price: float,
    ) -> Optional[Dict[str, Any]]:
        """
        Piazza un ordine Stop-Loss Market.
        
        Args:
            market: Es. "BTC/USDT"
            side: "sell" per chiudere long, "buy" per chiudere short
            quantity: Quantità da chiudere
            stop_price: Prezzo trigger dello stop
        """
        try:
            stop_price = self._round_price(stop_price, market)
            quantity = self._round_quantity(quantity, market)
            
            order = self.exchange.create_order(
                symbol=market,
                type="STOP_MARKET",
                side=side,
                amount=quantity,
                params={
                    "stopPrice": stop_price,
                    "reduceOnly": True,
                    "closePosition": False,
                }
            )
            logger.info(f"Stop-Loss piazzato: {side} {quantity} @ trigger {stop_price}")
            return order
        except Exception as e:
            logger.error(f"Errore piazzamento Stop-Loss: {e}")
            return None

    def _place_take_profit(
        self,
        market: str,
        side: str,
        quantity: float,
        take_profit_price: float,
    ) -> Optional[Dict[str, Any]]:
        """
        Piazza un ordine Take-Profit Market.
        """
        try:
            take_profit_price = self._round_price(take_profit_price, market)
            quantity = self._round_quantity(quantity, market)
            
            order = self.exchange.create_order(
                symbol=market,
                type="TAKE_PROFIT_MARKET",
                side=side,
                amount=quantity,
                params={
                    "stopPrice": take_profit_price,
                    "reduceOnly": True,
                    "closePosition": False,
                }
            )
            logger.info(f"Take-Profit piazzato: {side} {quantity} @ trigger {take_profit_price}")
            return order
        except Exception as e:
            logger.error(f"Errore piazzamento Take-Profit: {e}")
            return None

    def _cancel_open_orders(self, market: str) -> None:
        """Cancella tutti gli ordini aperti su un market (utile prima di chiudere posizione)."""
        try:
            open_orders = self.exchange.fetch_open_orders(market)
            for order in open_orders:
                try:
                    self.exchange.cancel_order(order['id'], market)
                    logger.debug(f"Ordine {order['id']} cancellato")
                except Exception as e:
                    logger.warning(f"Errore cancellazione ordine {order['id']}: {e}")
        except Exception as e:
            logger.warning(f"Errore fetch ordini aperti: {e}")

    def _find_position(self, market: str) -> Optional[Dict[str, Any]]:
        """Trova una posizione aperta per il market specificato."""
        positions: List[Dict[str, Any]] = self.exchange.fetch_positions([market])
        for p in positions:
            if p.get("symbol") != market:
                continue
            contracts = float(p.get("contracts", 0) or 0)
            if abs(contracts) > 0:
                return p
        return None

    def get_account_status_dict(self) -> Dict[str, Any]:
        """
        Restituisce lo stato completo dell'account.
        
        Returns:
            {
                "exchange": "binance_futures",
                "network": "testnet" | "mainnet",
                "balance_usd": float,
                "free_balance_usd": float,
                "open_positions": [...]
            }
        """
        balance = self.exchange.fetch_balance()
        usdt_info = balance.get("USDT", {})
        total = float(usdt_info.get("total", 0.0) or 0.0)
        free = float(usdt_info.get("free", 0.0) or 0.0)

        positions_raw: List[Dict[str, Any]] = self.exchange.fetch_positions()
        open_positions = []

        for p in positions_raw:
            contracts = float(p.get("contracts", 0) or 0)
            if abs(contracts) <= 0:
                continue

            symbol = p.get("symbol", "")
            base = symbol.split("/")[0]
            side = p.get("side") or p.get("positionSide") or "long"
            entry_price = float(p.get("entryPrice", 0) or 0)
            leverage = float(p.get("leverage", 1) or 1)
            unrealized_pnl = float(p.get("unrealizedPnl", 0) or 0)
            notional = float(p.get("notional", 0) or 0)

            open_positions.append({
                "symbol": base,
                "ccxt_symbol": symbol,
                "side": side,
                "size_contracts": contracts,
                "entry_price": entry_price,
                "leverage": leverage,
                "unrealized_pnl": unrealized_pnl,
                "notional_usd": notional,
            })

        return {
            "exchange": "binance_futures",
            "network": "testnet" if self.testnet else "mainnet",
            "balance_usd": total,
            "free_balance_usd": free,
            "open_positions": open_positions,
        }

    def execute_signal(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """
        Esegue un segnale di trading.
        
        Args:
            signal: Dizionario con operation, symbol, direction, etc.
            
        Returns:
            Risultato dell'esecuzione
        """
        operation = signal.get("operation", "hold")
        symbol = signal.get("symbol", "BTC").upper()
        direction = signal.get("direction", "long")
        target_portion = float(signal.get("target_portion_of_balance", 0.0) or 0.0)
        leverage = int(signal.get("leverage", 1) or 1)
        reason = signal.get("reason", "")

        market = self._market_symbol(symbol)

        logger.info(f"Esecuzione segnale: {operation} {symbol} {direction}")

        if operation == "hold":
            return {
                "status": "no_action",
                "operation": "hold",
                "symbol": symbol,
                "reason": reason or "Nessuna azione richiesta (hold).",
            }

        try:
            if operation == "open":
                return self._open_position(
                    market=market,
                    symbol=symbol,
                    direction=direction,
                    target_portion=target_portion,
                    leverage=leverage,
                    reason=reason,
                )
            elif operation == "close":
                return self._close_position(
                    market=market,
                    symbol=symbol,
                    direction=direction,
                    reason=reason,
                )
            else:
                return {
                    "status": "error",
                    "error": f"Operazione non supportata: {operation}",
                    "signal": signal,
                }
        except Exception as e:
            logger.exception(f"Errore esecuzione segnale: {e}")
            return {
                "status": "error",
                "error": str(e),
                "signal": signal,
            }

    def _open_position(
        self,
        *,
        market: str,
        symbol: str,
        direction: str,
        target_portion: float,
        leverage: int,
        reason: str = "",
    ) -> Dict[str, Any]:
        """Apre una nuova posizione con Stop-Loss e Take-Profit automatici."""
        
        # Verifica posizione esistente
        existing = self._find_position(market)
        if existing is not None:
            logger.warning(f"Posizione già esistente su {symbol}")
            return {
                "status": "skipped",
                "reason": f"Esiste già una posizione aperta su {symbol}",
                "existing_position": existing,
            }

        # Verifica balance
        free_usdt = self._get_free_usdt_balance()
        if free_usdt <= 0:
            return {
                "status": "error",
                "error": "Balance USDT disponibile nullo",
            }

        # Validazione target_portion
        if target_portion <= 0 or target_portion > 1:
            return {
                "status": "error",
                "error": f"target_portion_of_balance non valido: {target_portion}",
            }

        # OVERRIDE LEVA: massimo consentito per sicurezza
        leverage = min(leverage, MAX_LEVERAGE)

        # Calcola size
        notional = free_usdt * target_portion * leverage
        price = self._get_current_price(market)

        if price <= 0:
            return {
                "status": "error",
                "error": "Prezzo corrente non valido",
            }

        size = float(Decimal(str(notional)) / Decimal(str(price)))
        size = self._round_quantity(size, market)

        # Determina side
        if direction.lower() == "long":
            entry_side = "buy"
            sl_side = "sell"  # Per chiudere un long, vendi
            sl_price = price * (1 - DEFAULT_STOP_LOSS_PCT)
            tp_price = price * (1 + DEFAULT_TAKE_PROFIT_PCT)
        elif direction.lower() == "short":
            entry_side = "sell"
            sl_side = "buy"   # Per chiudere uno short, compra
            sl_price = price * (1 + DEFAULT_STOP_LOSS_PCT)
            tp_price = price * (1 - DEFAULT_TAKE_PROFIT_PCT)
        else:
            return {
                "status": "error",
                "error": f"Direzione non valida: {direction}",
            }

        # Imposta leva
        try:
            self.exchange.set_leverage(leverage, market)
            logger.info(f"Leva impostata a {leverage}x per {market}")
        except Exception as e:
            logger.warning(f"Impossibile impostare leva: {e}")

        # === ESEGUI ORDINE PRINCIPALE ===
        logger.info(f"Apertura {direction} {symbol}: size={size:.6f}, leva={leverage}x, prezzo~{price:.2f}")
        
        try:
            order = self.exchange.create_order(
                symbol=market,
                type="market",
                side=entry_side,
                amount=size,
                params={
                    "reduceOnly": False,
                },
            )
        except Exception as e:
            return {
                "status": "error",
                "error": f"Errore ordine principale: {e}",
            }

        logger.info(f"Ordine eseguito: {order.get('id', 'N/A')}")

        # === PIAZZA STOP-LOSS (CRITICO) ===
        sl_order = self._place_stop_loss(market, sl_side, size, sl_price)
        
        # === PIAZZA TAKE-PROFIT (OPZIONALE) ===
        tp_order = self._place_take_profit(market, sl_side, size, tp_price)

        return {
            "status": "filled",
            "action": "open",
            "symbol": symbol,
            "market": market,
            "direction": direction,
            "entry_price": price,
            "size": size,
            "leverage": leverage,
            "stop_loss_price": round(sl_price, 2),
            "take_profit_price": round(tp_price, 2),
            "stop_loss_order": sl_order.get('id') if sl_order else None,
            "take_profit_order": tp_order.get('id') if tp_order else None,
            "reason": reason,
            "ccxt_order": order,
        }

    def _close_position(
        self,
        *,
        market: str,
        symbol: str,
        direction: str,
        reason: str = "",
    ) -> Dict[str, Any]:
        """Chiude una posizione esistente e cancella ordini SL/TP pendenti."""
        
        existing = self._find_position(market)
        if existing is None:
            logger.warning(f"Nessuna posizione da chiudere su {symbol}")
            return {
                "status": "skipped",
                "reason": f"Nessuna posizione aperta trovata su {symbol}",
            }

        contracts = float(existing.get("contracts", 0) or 0)
        if contracts <= 0:
            return {
                "status": "skipped",
                "reason": f"Nessuna size > 0 per {symbol}",
                "existing_position": existing,
            }

        # === CANCELLA ORDINI SL/TP PENDENTI ===
        self._cancel_open_orders(market)

        # Determina side per chiusura
        side_pos = (existing.get("side") or existing.get("positionSide") or "long").lower()

        if side_pos == "long":
            side = "sell"
        elif side_pos == "short":
            side = "buy"
        else:
            # Fallback basato su direction
            if direction.lower() == "long":
                side = "sell"
            else:
                side = "buy"

        logger.info(f"Chiusura {side_pos} {symbol}: size={abs(contracts):.6f}")

        order = self.exchange.create_order(
            symbol=market,
            type="market",
            side=side,
            amount=abs(contracts),
            params={
                "reduceOnly": True,
            },
        )

        logger.info(f"Ordine chiusura eseguito: {order.get('id', 'N/A')}")

        return {
            "status": "filled",
            "action": "close",
            "symbol": symbol,
            "market": market,
            "reason": reason,
            "existing_position": existing,
            "ccxt_order": order,
        }
