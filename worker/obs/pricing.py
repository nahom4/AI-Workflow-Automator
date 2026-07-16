"""Provider/model token pricing — used to estimate cost_cents per call.

Numbers are public list rates as of 2026-02. Update when providers move them.
The free Gemini tier uses the same shadow cost so the dashboard can show
"if this were billed" totals (useful for forecasting when free quota is gone).

Units: USD cents per 1,000,000 tokens. Divide by 10,000 to get cents per
1,000 tokens, or by 10,000,000 to get cents per token.
"""

from __future__ import annotations

# {model: (input_cents_per_million, output_cents_per_million)}
_PRICES: dict[str, tuple[float, float]] = {
    # Groq
    "llama-3.3-70b-versatile": (59.0, 79.0),
    "llama-3.1-8b-instant": (5.0, 8.0),
    # Gemini (Google AI)
    "gemini-2.5-flash": (7.5, 30.0),
    "gemini-2.5-flash-lite": (10.0, 40.0),  # placeholder — adjust when GA pricing settles
    "gemini-2.0-flash": (10.0, 40.0),
    "gemini-2.5-pro": (125.0, 1000.0),
}


def estimate_cost_cents(model: str, tokens_in: int, tokens_out: int) -> float:
    """Return cost in cents (float) for `tokens_in` + `tokens_out` on `model`.

    Returns 0.0 for unknown models so the call still records — better to log
    zero than to drop the row.
    """
    cents_in, cents_out = _PRICES.get(model, (0.0, 0.0))
    return (cents_in * tokens_in + cents_out * tokens_out) / 1_000_000.0
