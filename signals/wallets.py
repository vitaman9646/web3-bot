import logging
from storage.db import get_wallet_stats, update_wallet_stat, update_clusters

logger = logging.getLogger(__name__)

_MIN_TRADES  = 5      # ignore wallets with fewer trades
_MIN_AVG_PNL = 1.2    # avg profit multiplier to be "smart"


async def is_smart_wallet(wallet: str) -> bool:
    stats = await get_wallet_stats(wallet)
    if not stats or stats["trades"] < _MIN_TRADES:
        return False
    avg = stats["profit"] / stats["trades"]
    return avg > _MIN_AVG_PNL


async def detect_wallet_activity(token_data: dict) -> float:
    """
    Returns a wallet score in [0, 0.5].

    ≥2 smart wallets → 0.5
    1  smart wallet  → 0.2
    0               → 0.0
    """
    buyers: list[str] = token_data.get("buyers", [])

    if not buyers:
        return 0.0

    # cluster tracking (fire-and-forget, non-blocking)
    await update_clusters(buyers)

    smart_count = 0
    for w in buyers:
        if await is_smart_wallet(w):
            smart_count += 1

    if smart_count >= 2:
        score = 0.5
    elif smart_count == 1:
        score = 0.2
    else:
        score = 0.0

    logger.debug("wallet_score=%s  smart=%d  token=%s",
                 score, smart_count, token_data.get("token"))
    return score


async def record_trade_outcome(buyers: list[str], profit: float):
    """Call after a trade closes to update per-wallet stats."""
    for w in buyers:
        await update_wallet_stat(w, profit)

