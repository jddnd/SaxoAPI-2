from dataclasses import dataclass
from typing import List

@dataclass
class OptionPlan:
    underlying_keywords: str   # e.g. "AAPL"
    expiry_iso: str            # 'YYYY-MM-DD'
    put_call: str              # 'Call' or 'Put'
    strike: float              # desired strike (fallback to nearest listed)
    entry_condition: str       # rule used by /signal or /tv
    tp_pct: float              # +% TP (1.0 = +100%)
    sl_pct: float              # -% SL (0.5 = -50%)

PLANS: List[OptionPlan] = [
    # Liquid SIM names — adjust expiry to a listed one (use /debug/option_space)
    OptionPlan("AAPL", "2025-08-22", "Call", 200.0, "price>=190", 0.8, 0.5),
    OptionPlan("MSFT", "2025-08-22", "Call", 450.0, "price>=430", 0.8, 0.5),
    OptionPlan("SPY",  "2025-08-22", "Call", 550.0, "price>=540", 0.8, 0.5),

    # RGLD roots exist in your SIM — keep if you want gold exposure
    OptionPlan("RGLD", "2025-09-19", "Call", 170.0, "GOLD>2500", 1.0, 0.3),
]
