from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass
class Position:
    side: int
    entry_time: str
    entry_price: float
    quantity: float
    sl_price: float
    tp_price: float
    atr_at_entry: float = 0.0
    trail_activated: bool = False
    highest_price: float = 0.0
    lowest_price: float = 0.0

    def to_dict(self) -> dict:
        return {
            "side": self.side,
            "entry_time": self.entry_time,
            "entry_price": self.entry_price,
            "quantity": self.quantity,
            "sl_price": self.sl_price,
            "tp_price": self.tp_price,
            "atr_at_entry": self.atr_at_entry,
            "trail_activated": self.trail_activated,
            "highest_price": self.highest_price,
            "lowest_price": self.lowest_price,
        }

    @staticmethod
    def from_dict(d: dict) -> "Position":
        return Position(**d)


def check_exit(
    pos: Position, high: float, low: float, close: float
) -> Tuple[Optional[str], Optional[float]]:
    is_long = pos.side == 1
    is_short = pos.side == -1

    if is_long:
        if low <= pos.sl_price:
            return ("sl", pos.sl_price)
        if high >= pos.tp_price:
            return ("tp", pos.tp_price)
    else:
        if high >= pos.sl_price:
            return ("sl", pos.sl_price)
        if low <= pos.tp_price:
            return ("tp", pos.tp_price)

    return (None, None)


def update_trail(
    pos: Position, high: float, low: float,
    trail_activation_atr: float, trail_offset_atr: float,
) -> Optional[float]:
    if pos.atr_at_entry <= 0 or trail_activation_atr <= 0:
        return None

    is_long = pos.side == 1
    atr = pos.atr_at_entry
    new_sl: Optional[float] = None

    if is_long:
        if high > pos.highest_price:
            pos.highest_price = high
        if not pos.trail_activated:
            if high - pos.entry_price >= trail_activation_atr * atr:
                pos.trail_activated = True
        if pos.trail_activated:
            candidate = pos.highest_price - trail_offset_atr * atr
            if candidate > pos.sl_price:
                pos.sl_price = candidate
                new_sl = candidate
    else:
        if low < pos.lowest_price:
            pos.lowest_price = low
        if not pos.trail_activated:
            if pos.entry_price - low >= trail_activation_atr * atr:
                pos.trail_activated = True
        if pos.trail_activated:
            candidate = pos.lowest_price + trail_offset_atr * atr
            if candidate < pos.sl_price:
                pos.sl_price = candidate
                new_sl = candidate

    return new_sl
