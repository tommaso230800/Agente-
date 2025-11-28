"""
Test Trading - Script per testare manualmente le funzionalità.

Esegue:
1. Verifica connessione Binance
2. Test apertura posizione
3. Test chiusura posizione
"""

import json
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()


def test_binance_connection():
    """Test connessione e stato account."""
    from binance_trader import BinanceFuturesTrader

    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")

    if not api_key or not api_secret:
        print("❌ BINANCE_API_KEY o BINANCE_API_SECRET mancanti nel .env")
        return False

    print("🔌 Test connessione Binance Futures Testnet...")

    try:
        bot = BinanceFuturesTrader(
            api_key=api_key,
            api_secret=api_secret,
            testnet=True,
        )

        status = bot.get_account_status_dict()
        print("\n📊 STATO ACCOUNT:")
        print(json.dumps(status, indent=2))

        print(f"\n✅ Connessione OK - Balance: ${status.get('balance_usd', 0):.2f}")
        return bot

    except Exception as e:
        print(f"❌ Errore connessione: {e}")
        return False


def test_open_close_position(bot):
    """Test apertura e chiusura posizione."""
    print("\n" + "=" * 50)
    print("📌 TEST: Apertura posizione LONG su BTC")
    print("=" * 50)

    open_signal = {
        "operation": "open",
        "symbol": "BTC",
        "direction": "long",
        "target_portion_of_balance": 0.05,  # Solo 5% per test
        "leverage": 2,
        "reason": "Test apertura da test_trading.py",
    }

    print(f"Segnale: {json.dumps(open_signal, indent=2)}")
    print("\nEsecuzione...")

    open_result = bot.execute_signal(open_signal)
    print(f"\nRisultato: {json.dumps(open_result, indent=2, default=str)}")

    if open_result.get("status") != "filled":
        print(f"⚠️ Posizione non aperta: {open_result.get('reason', open_result.get('error'))}")
        return

    print("\n⏳ Attendo 5 secondi...")
    time.sleep(5)

    # Chiusura
    print("\n" + "=" * 50)
    print("📌 TEST: Chiusura posizione LONG su BTC")
    print("=" * 50)

    close_signal = {
        "operation": "close",
        "symbol": "BTC",
        "direction": "long",
        "reason": "Test chiusura da test_trading.py",
    }

    print(f"Segnale: {json.dumps(close_signal, indent=2)}")
    print("\nEsecuzione...")

    close_result = bot.execute_signal(close_signal)
    print(f"\nRisultato: {json.dumps(close_result, indent=2, default=str)}")

    if close_result.get("status") == "filled":
        print("\n✅ Test apertura/chiusura completato con successo!")
    else:
        print(f"\n⚠️ Chiusura: {close_result.get('reason', close_result.get('error'))}")


def test_indicators():
    """Test recupero indicatori."""
    print("\n" + "=" * 50)
    print("📈 TEST: Recupero indicatori tecnici")
    print("=" * 50)

    try:
        from indicators import analyze_multiple_tickers

        tickers = ["BTC", "ETH"]
        print(f"Tickers: {tickers}")

        text, data = analyze_multiple_tickers(tickers, interval="15m")
        print("\n" + text)
        print("✅ Indicatori OK")
        return True

    except Exception as e:
        print(f"❌ Errore indicatori: {e}")
        return False


def test_ai_decision():
    """Test decisione AI (senza esecuzione)."""
    print("\n" + "=" * 50)
    print("🤖 TEST: Decisione AI")
    print("=" * 50)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("⚠️ OPENAI_API_KEY non impostata, skip test AI")
        return False

    try:
        from trading_agent import previsione_trading_agent

        test_prompt = """
        Portfolio: {"balance_usd": 1000, "open_positions": []}
        
        BTC: price=95000, RSI=45, MACD=positive
        
        Decide what to do.
        """

        print("Invio prompt di test...")
        decision = previsione_trading_agent(test_prompt)

        print(f"\nDecisione: {json.dumps(decision, indent=2)}")
        print("✅ AI Decision OK")
        return True

    except Exception as e:
        print(f"❌ Errore AI: {e}")
        return False


def main():
    """Esegue tutti i test."""
    print("=" * 60)
    print("  BINANCE TRADING AGENT - TEST SUITE")
    print("=" * 60)

    # Test connessione
    bot = test_binance_connection()
    if not bot:
        sys.exit(1)

    # Test indicatori
    test_indicators()

    # Test AI
    test_ai_decision()

    # Test trading (opzionale)
    print("\n" + "=" * 50)
    response = input("Vuoi eseguire il test di trading (apri/chiudi posizione)? [y/N]: ")
    if response.lower() == "y":
        test_open_close_position(bot)
    else:
        print("Test trading skippato")

    print("\n" + "=" * 60)
    print("  TEST COMPLETATI")
    print("=" * 60)


if __name__ == "__main__":
    main()
