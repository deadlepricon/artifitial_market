# symbols/registry.py
"""
Symbol registry: defines tradable pairs (e.g. BTC/USDT) and their metadata.
Architecture supports multiple symbols; order book and generator use this for
tick size, lot size, and display.
"""

from dataclasses import dataclass
from typing import Dict


@dataclass
class SymbolInfo:
    """Metadata for a single tradable symbol."""

    symbol: str
    base: str
    quote: str
    tick_size: float
    lot_size: float
    initial_mid_price: float

    def round_price(self, price: float) -> float:
        """Round price to tick size."""
        if self.tick_size <= 0:
            return price
        return round(price / self.tick_size) * self.tick_size

    def round_quantity(self, qty: float) -> float:
        """Round quantity to lot size."""
        if self.lot_size <= 0:
            return qty
        return round(qty / self.lot_size) * self.lot_size


# Global registry: symbol -> SymbolInfo
_registry: Dict[str, SymbolInfo] = {}


def register_symbol(info: SymbolInfo) -> None:
    """Register a symbol for trading."""
    _registry[info.symbol] = info


def get_symbol(symbol: str) -> SymbolInfo | None:
    """Return SymbolInfo for a symbol, or None if unknown."""
    return _registry.get(symbol)


def list_symbols() -> list[str]:
    """Return all registered symbol IDs."""
    return list(_registry.keys())


def ensure_default_symbols() -> None:
    """
    Register default symbols (BTC/USDT, ETH/USDT). Call at startup.
    Each gets its own order book, matching engine, and market generator.
    """
    from config.settings import (
        DEFAULT_INITIAL_MID_PRICE,
        DEFAULT_LOT_SIZE,
        DEFAULT_TICK_SIZE,
        ETH_INITIAL_MID_PRICE,
        TRADABLE_SYMBOLS,
    )

    initial_mid_by_symbol = {
        "BTC/USDT": DEFAULT_INITIAL_MID_PRICE,
        "ETH/USDT": ETH_INITIAL_MID_PRICE,
    }
    for sym in TRADABLE_SYMBOLS:
        if sym in _registry:
            continue
        base, quote = sym.split("/") if "/" in sym else (sym[:3], "USDT")
        mid = initial_mid_by_symbol.get(sym, DEFAULT_INITIAL_MID_PRICE)
        register_symbol(
            SymbolInfo(
                symbol=sym,
                base=base,
                quote=quote,
                tick_size=DEFAULT_TICK_SIZE,
                lot_size=DEFAULT_LOT_SIZE,
                initial_mid_price=mid,
            )
        )
