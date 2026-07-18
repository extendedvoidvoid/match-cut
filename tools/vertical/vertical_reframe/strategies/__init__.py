from __future__ import annotations

from vertical_reframe.strategies.center_crop import CenterCrop

STRATEGIES = {
    "center_crop": CenterCrop,
}


def get_strategy(name: str) -> CenterCrop:
    if name not in STRATEGIES:
        known = ", ".join(sorted(STRATEGIES))
        raise ValueError(f"Unknown strategy {name!r}. v1 implements: {known}")
    return STRATEGIES[name]()
