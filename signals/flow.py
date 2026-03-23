import logging

logger = logging.getLogger(__name__)


async def detect_flow(token_data: dict) -> float:
    """
    Returns a flow score in [0, 0.6].

    Criteria:
      - tx_count  > 30   → +0.2
      - volume    > 20k  → +0.2
      - liquidity > 30k  → +0.1  (deeper = safer entry)
      - age < 15 min     → +0.1  (very early)
    """
    score = 0.0

    tx      = token_data.get("tx_count",   0)
    volume  = token_data.get("volume",     0)
    liq     = token_data.get("liquidity",  0)
    age     = token_data.get("age_minutes", 999)

    if tx > 30:
        score += 0.2
    elif tx > 20:
        score += 0.1

    if volume > 30_000:
        score += 0.2
    elif volume > 15_000:
        score += 0.1

    if liq > 30_000:
        score += 0.1

    if age < 15:
        score += 0.1

    score = min(round(score, 3), 0.6)
    logger.debug("flow_score=%s  token=%s", score, token_data.get("token"))
    return score
