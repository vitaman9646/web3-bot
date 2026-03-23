import aiohttp
import time
import logging
from config import (
    MIN_LIQUIDITY_USD, MIN_VOLUME_H1, MIN_TX_H1,
    MAX_FDV_LIQ_RATIO, MAX_TOKEN_AGE_MINUTES,
)

logger = logging.getLogger(__name__)

DEX_URL = "https://api.dexscreener.com/latest/dex/pairs/solana"
_TIMEOUT = aiohttp.ClientTimeout(total=12)


async def fetch_pairs() -> list[dict]:
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.get(DEX_URL) as resp:
                if resp.status != 200:
                    logger.warning("Dexscreener status %s", resp.status)
                    return []
                data = await resp.json()
                return data.get("pairs") or []
    except Exception as exc:
        logger.error("fetch_pairs error: %s", exc)
        return []


# ── Filter helpers ─────────────────────────────────────────────────────────

def _age_minutes(pair: dict) -> float:
    created = pair.get("pairCreatedAt", 0)
    if not created:
        return 9999
    return (time.time() - created / 1000) / 60


def is_early(pair: dict) -> bool:
    return _age_minutes(pair) < MAX_TOKEN_AGE_MINUTES


def is_safe(pair: dict) -> bool:
    liquidity = float((pair.get("liquidity") or {}).get("usd", 0))
    fdv       = float(pair.get("fdv") or 0)

    if liquidity < MIN_LIQUIDITY_USD:
        return False
    if fdv > 0 and fdv > liquidity * MAX_FDV_LIQ_RATIO:
        return False
    return True


def is_fake_volume(pair: dict) -> bool:
    txns  = pair.get("txns", {}).get("h1", {})
    buys  = txns.get("buys",  0)
    sells = txns.get("sells", 0)
    # suspiciously one-sided
    if sells == 0:
        return True
    if buys > sells * 5:
        return True
    return False


def filter_tokens(pairs: list[dict]) -> list[dict]:
    results = []
    for p in pairs:
        txns      = p.get("txns", {}).get("h1", {})
        buys      = txns.get("buys", 0)
        volume    = float((p.get("volume") or {}).get("h1", 0))
        liquidity = float((p.get("liquidity") or {}).get("usd", 0))

        if buys < MIN_TX_H1:
            continue
        if volume < MIN_VOLUME_H1:
            continue
        if not is_early(p):
            continue
        if not is_safe(p):
            continue
        if is_fake_volume(p):
            continue

        results.append(
            {
                "token":       p["baseToken"]["symbol"],
                "mint":        p["baseToken"]["address"],
                "tx_count":    buys,
                "volume":      volume,
                "liquidity":   liquidity,
                "age_minutes": _age_minutes(p),
                "buyers":      [],   # enriched later via Helius / on-chain
                "price_usd":   float(p.get("priceUsd") or 0),
            }
        )

    logger.debug("filter_tokens: %d / %d passed", len(results), len(pairs))
    return results
