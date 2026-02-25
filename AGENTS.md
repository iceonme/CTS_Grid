# CTS1 - Grid RSI Trading System (AGENTS.md)

## Project Overview

**CTS1 (Crypto Trade Squad)** is a dynamic grid + RSI strategy trading system for cryptocurrency trading. This is the **refactored version (V2.4-ULTRA)** with a clean layered architecture.

- **Main Language**: Python 3.x
- **Project Type**: Algorithmic Trading System
- **Exchange**: OKX (with demo/live trading support)
- **Strategy**: Dynamic Grid + RSI (Relative Strength Index)

## Architecture

The system follows a strict layered architecture with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────┐
│  Application Layer                                       │
│  ├── main.py              # Unified entry point          │
│  ├── run_backtest.py      # Backtest entry               │
│  ├── run_paper.py         # Paper trading entry          │
│  ├── run_live.py          # Live trading entry           │
│  └── run_okx_demo.py      # OKX demo one-click start     │
├─────────────────────────────────────────────────────────┤
│  Engine Layer (Engines)                                  │
│  ├── backtest.py          # Event-driven backtest        │
│  └── live.py              # Live trading engine          │
├─────────────────────────────────────────────────────────┤
│  Strategy Layer (Strategies)                             │
│  ├── base.py              # Strategy base class          │
│  └── grid_rsi.py          # Grid RSI strategy V4         │
├─────────────────────────────────────────────────────────┤
│  Execution Layer (Executors)                             │
│  ├── base.py              # Executor base class          │
│  ├── paper.py             # Paper/simulated trading      │
│  └── okx.py               # OKX real execution           │
├─────────────────────────────────────────────────────────┤
│  Data Layer (DataFeeds)                                  │
│  ├── base.py              # Data interface               │
│  ├── csv_feed.py          # CSV historical data          │
│  └── okx_feed.py          # OKX real-time data           │
├─────────────────────────────────────────────────────────┤
│  Core Layer (Core)                                       │
│  └── types.py             # Shared data types            │
├─────────────────────────────────────────────────────────┤
│  Dashboard Layer                                         │
│  └── server.py            # Flask + SocketIO monitoring  │
└─────────────────────────────────────────────────────────┘
```

### Key Design Principles

1. **Stateless Strategies**: Strategies are stateless and do not maintain positions/capital. They only output signals.
2. **Single Source of Truth**: Engines maintain the capital and positions.
3. **Pure Function Design**: Strategies receive market data + context, return signals.
4. **Pluggable Architecture**: Easy to switch between paper and live execution.

## Technology Stack

### Core Dependencies
```
pandas          # Data processing
numpy           # Numerical computing
flask           # Web dashboard
flask-socketio  # Real-time WebSocket
requests        # HTTP API calls
```

### External APIs
- **OKX API V5**: For live trading and real-time data
  - REST API for order placement
  - REST API for market data (polling mode, 2s interval)

### Frontend (Dashboard)
- **TradingView Lightweight Charts**: For candlestick charts
- **Socket.IO Client**: Real-time data updates
- Pure HTML/CSS/JavaScript (no framework)

## Directory Structure

```
cts_grid/
├── core/                   # Core type definitions
│   ├── __init__.py
│   └── types.py            # Signal, Order, Position, MarketData, etc.
├── strategies/             # Strategy layer
│   ├── __init__.py
│   ├── base.py             # BaseStrategy abstract class
│   └── grid_rsi.py         # GridRSIStrategy V4 implementation
├── executors/              # Execution layer
│   ├── __init__.py
│   ├── base.py             # BaseExecutor abstract class
│   ├── paper.py            # PaperExecutor (simulation)
│   └── okx.py              # OKXExecutor (real trading)
├── datafeeds/              # Data layer
│   ├── __init__.py
│   ├── base.py             # BaseDataFeed abstract class
│   ├── csv_feed.py         # CSVDataFeed (historical)
│   └── okx_feed.py         # OKXDataFeed (real-time)
├── engines/                # Engine layer
│   ├── __init__.py
│   ├── backtest.py         # BacktestEngine
│   └── live.py             # LiveEngine
├── dashboard/              # Monitoring dashboard
│   ├── __init__.py
│   ├── server.py           # Flask + SocketIO server
│   └── templates/
│       └── dashboard.html  # Frontend template
├── config/                 # Configuration
│   ├── __init__.py
│   ├── api_config.py       # API credentials (in repo)
│   ├── api_config.example.py
│   └── okx_config.py       # OKXAPI class implementation
├── tests/                  # Unit tests
│   ├── __init__.py
│   ├── test_strategy.py    # Strategy tests
│   └── test_executor_fixes.py
├── templates/              # HTML templates
│   └── dashboard.html
├── main.py                 # Unified CLI entry
├── run_backtest.py         # Backtest script
├── run_paper.py            # Paper trading script
├── run_live.py             # Live trading script
├── run_okx_demo.py         # OKX demo trading script
├── grid_strategy.py        # Legacy strategy (V4 standalone)
├── paper_trading.py        # Legacy paper trading
├── readme.md               # Chinese documentation
├── HANDOVER.md             # Project handover notes
└── .gitignore
```

## Running Modes

### 1. Backtest Mode
```bash
python main.py backtest --data btc_1m.csv --capital 10000
# or
python run_backtest.py --data btc_1m.csv
```

### 2. Paper Trading Mode (with Dashboard)
```bash
python main.py paper --data btc_1m.csv --port 5000
# Then visit http://localhost:5000
```

### 3. Live Trading Mode (OKX Demo)
```bash
# Set environment variables
export OKX_API_KEY="your_key"
export OKX_SECRET="your_secret"
export OKX_PASSPHRASE="your_passphrase"

python main.py live --demo
```

### 4. OKX Demo One-Click Start
```bash
python run_okx_demo.py
```

## Configuration

### API Configuration

API credentials are stored in `config/api_config.py` (currently in the repo per user request):

```python
OKX_DEMO_CONFIG = {
    'api_key': 'YOUR_API_KEY',
    'api_secret': 'YOUR_API_SECRET',
    'passphrase': 'YOUR_PASSPHRASE',
    'is_demo': True
}
```

### Strategy Parameters

Key parameters for `GridRSIStrategy`:

```python
strategy = GridRSIStrategy(
    symbol="BTC-USDT",
    # Grid parameters
    grid_levels=10,              # Number of grid levels
    grid_refresh_period=100,     # Grid refresh period (candles)
    grid_buffer_pct=0.1,         # Grid buffer percentage
    # RSI parameters
    rsi_period=14,
    rsi_oversold=35,
    rsi_overbought=65,
    adaptive_rsi=True,           # Dynamic RSI thresholds
    # Position parameters
    base_position_pct=0.1,       # Base position size (10% of capital)
    max_positions=5,             # Max position layers
    use_kelly_sizing=True,       # Kelly criterion sizing
    # Stop loss parameters
    stop_loss_pct=0.05,
    trailing_stop=True,
)
```

## Core Data Types (core/types.py)

| Type | Description |
|------|-------------|
| `Signal` | Strategy output: timestamp, symbol, side, size, price, confidence |
| `Order` | Order sent to executor: order_id, symbol, side, size, type |
| `FillEvent` | Execution result: order_id, filled_size, filled_price, fee, pnl |
| `Position` | Current position: symbol, size, avg_price, unrealized_pnl |
| `MarketData` | OHLCV data: timestamp, open, high, low, close, volume |
| `StrategyContext` | Context provided by engine: cash, positions, current_prices |
| `PortfolioSnapshot` | Portfolio state: timestamp, cash, positions, total_value |

## Testing

### Run Unit Tests
```bash
# Run all strategy tests
python -m pytest tests/test_strategy.py -v

# Run specific test
python -m pytest tests/test_strategy.py::TestGridRSIStrategy::test_rsi_calculation -v
```

### Test Coverage
- Strategy initialization
- Signal generation
- RSI calculation
- Position size calculation

## Development Conventions

### Code Style
- **Comments**: Chinese (项目主要使用中文注释)
- **Variable names**: Mixed English with Chinese comments
- **Type hints**: Extensively used
- **Docstrings**: Google style with Chinese descriptions

### Module Organization
1. Each layer has `__init__.py` with `__all__` exports
2. Abstract base classes define the interface
3. Concrete implementations inherit from base classes
4. All types centralized in `core/types.py`

### Error Handling
- Use `try/except` with traceback printing for debugging
- Order rejection reasons stored in `order.meta['reject_reason']`
- Graceful degradation for API failures

## Known Issues and TODOs

### Current Status (from HANDOVER.md)
- ✅ OKX API authentication fixed (401 errors resolved)
- ✅ Real-time balance sync (every 5 minutes)
- ✅ Dashboard K-line rendering fixed
- ✅ Order placement working

### Planned Tasks

**P0 (High Priority)**:
- Complete server mode transition (`force_server=True` for all orders)
- Handle minimum order size limits (OKX error 51020)

**P1 (Medium Priority)**:
- Improve Kelly formula calculation for exchange precision
- Add automatic strategy reset on balance突变

**P2 (Low Priority)**:
- Add manual buttons: "Refresh Balance", "Force Close/Reset Grid"
- Clean up legacy files (`generate_mock_data.py`, etc.)

### Technical Debt
- WebSocket data feed not implemented (currently polling)
- Order cancellation not fully implemented
- Complete order lifecycle management pending

## Security Considerations

1. **API Credentials**: Currently stored in `config/api_config.py` (in repo)
   - In production, use environment variables instead
2. **Demo Mode**: Default is demo trading (`is_demo=True`)
3. **Signature Algorithm**: HMAC-SHA256 with proper timestamp handling

## Entry Points Summary

| Script | Purpose | Key Parameters |
|--------|---------|----------------|
| `main.py` | Unified CLI | `backtest/paper/live` subcommands |
| `run_backtest.py` | Quick backtest | `--data`, `--capital` |
| `run_paper.py` | Paper trading | `--data`, `--port` |
| `run_live.py` | Live trading | `--demo`, `--symbol` |
| `run_okx_demo.py` | OKX demo (simple) | Uses `config/api_config.py` |

## Common Commands

```bash
# Install dependencies
pip install pandas numpy flask flask-socketio requests

# Run backtest
python main.py backtest --data btc_1m.csv

# Run paper trading with dashboard
python main.py paper --data btc_1m.csv --port 5000

# Run OKX demo
python run_okx_demo.py

# Run tests
python -m pytest tests/test_strategy.py -v
```

## Notes for AI Agents

1. **Language**: Comments and documentation are primarily in Chinese
2. **Strategy Logic**: Grid RSI V4 uses pivot points (3 highs, 3 lows) for dynamic grid calculation
3. **Order Size Semantics**: 
   - BUY signals: `size` is in quote currency (USDT amount)
   - SELL signals: `size` is in base currency (BTC amount)
   - Controlled by `meta['size_in_quote']` flag
4. **Architecture**: Always maintain separation between strategy (signal) and executor (action)
5. **Testing**: Use `PaperExecutor` for safe testing before touching real APIs
