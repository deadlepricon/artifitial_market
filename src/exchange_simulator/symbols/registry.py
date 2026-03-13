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
    Register default symbol (BTC/USDT). Call at startup.
    Add more symbols here for multi-symbol support.
    """
    from config.settings import (
        DEFAULT_INITIAL_MID_PRICE,
        DEFAULT_LOT_SIZE,
        DEFAULT_SYMBOL,
        DEFAULT_TICK_SIZE,
    )

    if DEFAULT_SYMBOL not in _registry:
        base, quote = DEFAULT_SYMBOL.split("/") if "/" in DEFAULT_SYMBOL else ("BTC", "USDT")
        register_symbol(
            SymbolInfo(
                symbol=DEFAULT_SYMBOL,
                base=base,
                quote=quote,
                tick_size=DEFAULT_TICK_SIZE,
                lot_size=DEFAULT_LOT_SIZE,
                initial_mid_price=DEFAULT_INITIAL_MID_PRICE,
            )
        )
