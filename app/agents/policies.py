"""
Business guardrails used by autonomous financial agents.
"""

from __future__ import annotations

from typing import Any, Dict

# Governance matrix (approved by CFO roadmap)
MAX_AUTONOMOUS_GRACE_DAYS = 5
MAX_AUTONOMOUS_DISCOUNT_PCT = 10.0
MAX_AUTONOMOUS_DISCOUNT_VALUE_BRL = 3000.0
MAX_AUTONOMOUS_INSTALLMENTS = 3
MANDATORY_CFO_APPROVAL_ABOVE_BRL = 20000.0


def evaluate_negotiation_guardrails(
    *,
    invoice_value_brl: float,
    requested_discount_pct: float = 0.0,
    requested_discount_value_brl: float = 0.0,
    requested_installments: int = 1,
    requested_grace_days: int = 0,
) -> Dict[str, Any]:
    """
    Evaluate whether a proposed negotiation can be approved autonomously.
    """
    reasons = []

    if requested_grace_days > MAX_AUTONOMOUS_GRACE_DAYS:
        reasons.append(
            f"prazo_adicional>{MAX_AUTONOMOUS_GRACE_DAYS}d"
        )

    if requested_discount_pct > MAX_AUTONOMOUS_DISCOUNT_PCT:
        reasons.append(
            f"desconto_pct>{MAX_AUTONOMOUS_DISCOUNT_PCT:.1f}%"
        )

    if requested_discount_value_brl > MAX_AUTONOMOUS_DISCOUNT_VALUE_BRL:
        reasons.append(
            f"desconto_valor>{MAX_AUTONOMOUS_DISCOUNT_VALUE_BRL:.2f}"
        )

    if requested_installments > MAX_AUTONOMOUS_INSTALLMENTS:
        reasons.append(
            f"parcelas>{MAX_AUTONOMOUS_INSTALLMENTS}"
        )

    if invoice_value_brl > MANDATORY_CFO_APPROVAL_ABOVE_BRL:
        reasons.append(
            f"valor_titulo>{MANDATORY_CFO_APPROVAL_ABOVE_BRL:.2f}"
        )

    return {
        "autonomous_allowed": len(reasons) == 0,
        "escalate_to_cfo": len(reasons) > 0,
        "reasons": reasons,
    }
