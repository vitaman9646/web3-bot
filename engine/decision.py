import logging
import sqlite3
from config import (
    FLOW_WEIGHT, WALLET_WEIGHT, SCORE_THRESHOLD,
    ML_ENABLED, ML_MIN_SAMPLES, ML_PROBA_THRESHOLD, DB_PATH,
)

logger = logging.getLogger(__name__)

# mutable — updated by learning module
_weights = {"flow": FLOW_WEIGHT, "wallet": WALLET_WEIGHT}


class DecisionEngine:
    def __init__(self):
        self._ml_model = None
        self._ml_ready = False

    # ── ML plumbing ────────────────────────────────────────────────────────

    def load_ml_model(self):
        if not ML_ENABLED:
            return
        try:
            from ml.model import load_model
            self._ml_model = load_model()
            self._ml_ready = self._ml_model is not None
            logger.info("ML model loaded: %s", self._ml_ready)
        except Exception as exc:
            logger.warning("ML model not loaded: %s", exc)

    # ── Main decision ──────────────────────────────────────────────────────

    def decide(
        self,
        token_data: dict,
        flow_score: float,
        wallet_score: float,
    ) -> tuple[bool, float, float | None]:
        """
        Returns (should_trade, final_score, ml_proba).
        """
        score = (
            flow_score   * _weights["flow"]   +
            wallet_score * _weights["wallet"]
        )

        # slight penalty for low volume even if scores pass
        if token_data.get("volume", 0) < 15_000:
            score -= 0.1

        score = round(max(score, 0.0), 4)

        ml_proba = None
        if self._ml_ready and ML_ENABLED:
            ml_proba = self._predict(token_data, flow_score, wallet_score)
            if ml_proba < ML_PROBA_THRESHOLD:
                logger.debug("ML blocked: proba=%.3f  token=%s",
                             ml_proba, token_data.get("token"))
                return False, score, ml_proba

        should_trade = score >= SCORE_THRESHOLD
        logger.debug("decision=%s  score=%.4f  token=%s",
                     should_trade, score, token_data.get("token"))
        return should_trade, score, ml_proba

    def _predict(self, token_data, flow, wallet) -> float:
        try:
            features = [[
                flow,
                wallet,
                token_data.get("volume",    0),
                token_data.get("tx_count",  0),
                token_data.get("liquidity", 0),
                token_data.get("age_minutes", 30),
            ]]
            proba = self._ml_model.predict_proba(features)[0][1]
            return float(proba)
        except Exception as exc:
            logger.warning("ML predict error: %s", exc)
            return 1.0   # fallback: don't block

    # ── Weight update ──────────────────────────────────────────────────────

    def update_weights(self, new_flow: float, new_wallet: float):
        _weights["flow"]   = round(new_flow,   4)
        _weights["wallet"] = round(new_wallet, 4)
        logger.info("Weights updated: flow=%.3f  wallet=%.3f",
                    _weights["flow"], _weights["wallet"])

    @property
    def weights(self) -> dict:
        return dict(_weights)

    # ── ML data-readiness check ────────────────────────────────────────────

    @staticmethod
    def has_enough_data() -> bool:
        try:
            conn = sqlite3.connect(DB_PATH)
            n = conn.execute(
                "SELECT COUNT(*) FROM trades WHERE status='closed'"
            ).fetchone()[0]
            conn.close()
            return n >= ML_MIN_SAMPLES
        except Exception:
            return False
