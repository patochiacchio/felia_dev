from typing import Dict, Iterable

IN_STOCK_BONUS = 5
MUST_BONUS = 2
Q_BONUS = 1
NOT_PENALTY = 3

# Scoring simple y transparente
def _contains(text: str, tokens: Iterable[str]) -> int:
    t = text.lower()
    return sum(1 for tok in tokens if tok and tok.lower() in t)

def score_item(item: Dict, must_tokens, not_tokens, q_tokens) -> int:
    name = item.get("name", "")
    code = item.get("default_code", "")
    text = f"{name} {code}".lower()

    score = 0
    if (item.get("qty_available", 0) or 0) > 0:
        score += IN_STOCK_BONUS

    score += MUST_BONUS * _contains(text, must_tokens)
    score += Q_BONUS * _contains(text, q_tokens)
    score -= NOT_PENALTY * _contains(text, not_tokens)

    return score
