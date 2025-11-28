# Binance Trading Agent 🤖

Trading bot **completamente autonomo** per Binance Futures con decisioni AI e risk management automatico.

## ✨ Caratteristiche

- **100% Autonomo** - Una volta avviato, non richiede intervento umano
- **Stop-Loss Automatico** - 2% su ogni trade (protegge da flash crash)
- **Take-Profit Automatico** - 4% su ogni trade (ratio 1:2)
- **Leva Massima 5x** - Limitata dal sistema per sicurezza
- **Economico** - Default: gpt-4o-mini + cicli ogni 15 min (~$1-2/mese)
- **Deploy Railway** - Funziona 24/7 anche con PC spento

## 🛡️ Risk Management Automatico

Il bot gestisce il rischio **senza intervento umano**:

| Parametro | Valore | Descrizione |
|-----------|--------|-------------|
| Stop-Loss | 2% | Ordine piazzato su Binance, attivo anche se bot offline |
| Take-Profit | 4% | Ratio rischio/rendimento 1:2 |
| Max Leverage | 5x | Sistema ignora richieste AI > 5x |
| Position Size | 10-30% | Suggerito all'AI, tu non devi fare nulla |

**Importante**: SL/TP sono ordini reali su Binance. Se Railway crasha, sei comunque protetto.

## 🏗️ Architettura
┌─────────────────────────────────────────────────────────────┐
│                        main.py                               │
│                   (Loop Continuo)                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ indicators   │  │  news_feed   │  │  sentiment   │       │
│  │   (ccxt)     │  │    (RSS)     │  │    (CMC)     │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐                         │
│  │  forecaster  │  │  whalealert  │                         │
│  │  (Prophet)   │  │   (API)      │                         │
│  └──────────────┘  └──────────────┘                         │
│                                                              │
│                         ▼                                    │
│              ┌──────────────────┐                           │
│              │  trading_agent   │                           │
│              │    (OpenAI)      │                           │
│              └──────────────────┘                           │
│                         ▼                                    │
│              ┌──────────────────┐                           │
│              │ binance_trader   │                           │
│              │    (ccxt)        │                           │
│              └──────────────────┘                           │
│                         ▼                                    │
│              ┌──────────────────┐                           │
│              │    db_utils      │                           │
│              │  (PostgreSQL)    │                           │
│              └──────────────────┘                           │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### 1. Clone e Setup

```bash
git clone <repository>
cd binance-trading-agent

# Crea ambiente virtuale
python -m venv venv
source venv/bin/activate  # macOS/Linux
# oppure: venv\Scripts\activate  # Windows

# Installa dipendenze
pip install -r requirements.txt
```

### 2. Configurazione

```bash
# Copia il template
cp .env.example .env

# Modifica .env con le tue API keys
```

**Variabili obbligatorie:**
- `BINANCE_API_KEY` - API key Binance Futures
- `BINANCE_API_SECRET` - Secret Binance Futures
- `OPENAI_API_KEY` - API key OpenAI
- `DATABASE_URL` - URL PostgreSQL

**Ottenere le API keys:**
- **Binance Testnet**: https://testnet.binancefuture.com/
- **OpenAI**: https://platform.openai.com/api-keys
- **CoinMarketCap** (opzionale): https://pro.coinmarketcap.com/

### 3. Database

Il bot usa PostgreSQL per il logging. Puoi usare:

**Locale (Docker):**
```bash
docker run -d --name trading-db \
  -e POSTGRES_USER=trading \
  -e POSTGRES_PASSWORD=trading123 \
  -e POSTGRES_DB=trading_db \
  -p 5432:5432 \
  postgres:15

# .env
DATABASE_URL=postgresql://trading:trading123@localhost:5432/trading_db
```

**Railway PostgreSQL:**
Railway fornisce `DATABASE_URL` automaticamente quando aggiungi un database PostgreSQL al progetto.

### 4. Test Locale

```bash
# Verifica configurazione
python test_trading.py

# Esegui il bot (ctrl+c per fermare)
python main.py
```

## 🚂 Deploy su Railway

### 1. Setup Progetto

1. Vai su [railway.app](https://railway.app)
2. Crea nuovo progetto
3. Connetti il repository GitHub

### 2. Aggiungi PostgreSQL

1. Click "New" → "Database" → "PostgreSQL"
2. Railway imposta `DATABASE_URL` automaticamente

### 3. Configura Variabili

In Railway dashboard → Variables, aggiungi:

```
BINANCE_API_KEY=xxx
BINANCE_API_SECRET=xxx
OPENAI_API_KEY=xxx
CMC_PRO_API_KEY=xxx (opzionale)
TESTNET=true
LOOP_INTERVAL_SECONDS=900
```

### 4. Deploy

Railway rileva automaticamente `railway.json` o `Procfile` e avvia il bot.

## ⚙️ Configurazione Avanzata

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `TESTNET` | `true` | Usa testnet Binance |
| `TICKERS` | `BTC,ETH,SOL` | Coins da monitorare |
| `LOOP_INTERVAL_SECONDS` | `900` | Intervallo tra cicli (secondi, 15 min default) |
| `OPENAI_MODEL` | `gpt-4o-mini` | Modello AI (economico di default) |
| `DRY_RUN` | `false` | Logga senza eseguire ordini |
| `ENABLE_NEWS` | `true` | Abilita feed news |
| `ENABLE_SENTIMENT` | `true` | Abilita Fear & Greed |
| `ENABLE_WHALE_ALERTS` | `true` | Abilita whale tracking |
| `ENABLE_FORECASTS` | `true` | Abilita previsioni Prophet |

## 📊 Monitoraggio

### Logs Railway

```bash
railway logs
```

### Query Database

```sql
-- Ultime operazioni
SELECT created_at, operation, symbol, direction, 
       target_portion_of_balance, leverage
FROM bot_operations 
ORDER BY created_at DESC 
LIMIT 20;

-- Errori recenti
SELECT created_at, error_type, error_message, source
FROM errors
ORDER BY created_at DESC
LIMIT 10;
```

## 🔒 Sicurezza

- ⚠️ **Mai committare `.env`** - È nel `.gitignore`
- ⚠️ **Usa sempre testnet** prima del mainnet
- ⚠️ **Imposta limiti** su API keys Binance (IP whitelist, withdrawal disabled)
- ⚠️ **Monitora** regolarmente le operazioni

## 📁 Struttura File

```
binance-trading-agent/
├── main.py              # Entry point, loop principale
├── config.py            # Configurazione centralizzata
├── binance_trader.py    # Wrapper ccxt per ordini
├── trading_agent.py     # Decisioni AI (OpenAI)
├── indicators.py        # Indicatori tecnici
├── forecaster.py        # Previsioni Prophet
├── news_feed.py         # Feed RSS news
├── sentiment.py         # Fear & Greed Index
├── whalealert.py        # Whale movements
├── db_utils.py          # Logging PostgreSQL
├── system_prompt.txt    # Template prompt AI
├── test_trading.py      # Test suite
├── requirements.txt     # Dipendenze Python
├── railway.json         # Config Railway
├── Procfile             # Alternativa Railway
├── .env.example         # Template variabili
└── README.md            # Questa documentazione
```

## 🐛 Troubleshooting

**"BINANCE_API_KEY non impostata"**
→ Verifica che `.env` contenga le variabili corrette

**"Errore connessione database"**
→ Verifica `DATABASE_URL` e che PostgreSQL sia raggiungibile

**"OpenAI Error: model not found"**
→ Verifica `OPENAI_MODEL` (usa `gpt-4o`, `gpt-4-turbo`, o `gpt-3.5-turbo`)

**"Posizione già esistente"**
→ Il bot non apre posizioni duplicate sullo stesso coin

## 📜 License

MIT License

---

> Sviluppato da Rizzo AI Academy
