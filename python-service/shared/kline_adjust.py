"""K-line price adjustment (复权) preference for A-share HTTP sources."""
from __future__ import annotations

from typing import Literal

KlineAdjust = Literal["qfq", "hfq", "none"]

_DEFAULT: KlineAdjust = "qfq"
_current: KlineAdjust = _DEFAULT


def set_kline_adjust(adjust: str | None) -> None:
    global _current
    key = str(adjust or "qfq").strip().lower()
    if key in ("qfq", "hfq", "none"):
        _current = key  # type: ignore[assignment]
    else:
        _current = _DEFAULT


def get_kline_adjust() -> KlineAdjust:
    return _current


def apply_kline_adjust_from_settings(settings: object | None) -> None:
    if settings is None:
        set_kline_adjust(_DEFAULT)
        return
    general = getattr(settings, "general", settings)
    set_kline_adjust(getattr(general, "kline_adjust", _DEFAULT))
