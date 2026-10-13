"""
NativeReferenceSizing — moteur de dimensionnement fail-closed (P1-C, chantier §11).

Repond uniquement a la question : etant donne une SizingPolicy explicite et
l'etat reel du portefeuille (PortfolioState), quelle quantite ce
StrategyCandidate peut-il proposer ?

Regles produit V1 (deliberement restrictives) :
  - Aucune valeur financiere n'est jamais devinee. Policy/prix/equity/
    increment manquants ou invalides => REJECTED explicite, jamais 0 discret
    ou une valeur par defaut favorable.
  - BUY peut ouvrir/augmenter une position LONGUE, plafonnee par chaque
    contrainte CONFIGUREE de la policy (le plafond le plus restrictif
    l'emporte).
  - SELL ne fait QUE reduire une position LONGUE existante. V1 ne supporte
    pas l'ouverture ou l'augmentation d'un SHORT. Reduire du risque n'est
    jamais bloque par drawdown/exposition/concentration : ces contraintes ne
    limitent que l'AJOUT de risque.
  - Aucun multiplicateur de confiance, de volatilite, de Sigma ou de risque
    par trade n'est applique. StrategyCandidate.confidence reste une preuve,
    pas un multiplicateur de taille, en V1.

Sizing != Strategy, Sizing != KX108, Sizing != Binder, Sizing != Broker :
ce module ne produit ni Authority.ACT, ni receipt, ni ordre broker. Il ne
fait qu'evaluer une SizingDecision.
"""
from __future__ import annotations

from decimal import ROUND_DOWN, Decimal, InvalidOperation
from typing import Dict, Optional, Tuple

from domain.market import MarketSnapshot
from domain.portfolio import PortfolioState
from domain.proposal import SizingDecision, StrategyCandidate
from domain.types import Side
from native.sizing.sizing_policy import SizingPolicy


def _normalize_down(quantity: float, increment: float) -> float:
    """
    Arrondit `quantity` vers le bas au multiple de `increment` le plus proche,
    sans jamais depasser `quantity`. Utilise Decimal (via la representation
    str() des floats) pour eviter les artefacts de virgule flottante binaire
    (ex: 10.37 / 0.1 ne doit pas devenir 103.699999...).

    Exemples : (10.37, 0.1) -> 10.3 ; (10.37, 1) -> 10.0.
    """
    if quantity <= 0 or increment <= 0:
        return 0.0
    try:
        d_quantity = Decimal(str(quantity))
        d_increment = Decimal(str(increment))
        steps = (d_quantity / d_increment).to_integral_value(rounding=ROUND_DOWN)
        result = steps * d_increment
    except (InvalidOperation, ArithmeticError):
        return 0.0
    result_float = float(result)
    return result_float if result_float > 0 else 0.0


class NativeReferenceSizing:
    """
    Implementation native, deterministe et pure de SizingPort. Ne fait aucun
    appel reseau, ne lit aucune configuration cachee : tout provient des
    parametres explicites de size().
    """

    def __init__(self, policy: Optional[SizingPolicy] = None) -> None:
        self._policy = policy

    def size(
        self,
        candidate: StrategyCandidate,
        snapshot: MarketSnapshot,
        portfolio: Optional[PortfolioState],
    ) -> SizingDecision:
        policy = self._policy

        # --- C. Configuration fail-closed --------------------------------
        if policy is None:
            return SizingDecision(
                quantity=0.0,
                requested_quantity=0.0,
                status="REJECTED",
                rationale="SIZING_POLICY_NOT_CONFIGURED",
            )
        if not policy.has_valid_quantity_increment:
            return SizingDecision(
                quantity=0.0,
                requested_quantity=0.0,
                status="REJECTED",
                rationale="QUANTITY_INCREMENT_NOT_CONFIGURED",
            )
        if not policy.has_sizing_base:
            return SizingDecision(
                quantity=0.0,
                requested_quantity=0.0,
                status="REJECTED",
                rationale="SIZING_TARGET_NOT_CONFIGURED",
            )

        # --- D. Entrees reelles requises ----------------------------------
        if snapshot is None or snapshot.last_price is None or snapshot.last_price <= 0:
            return SizingDecision(
                quantity=0.0,
                requested_quantity=0.0,
                status="REJECTED",
                rationale="INVALID_MARKET_PRICE",
            )
        if portfolio is None or portfolio.account is None:
            return SizingDecision(
                quantity=0.0,
                requested_quantity=0.0,
                status="REJECTED",
                rationale="PORTFOLIO_STATE_NOT_CONFIGURED",
            )
        equity = portfolio.account.equity
        if equity is None or equity <= 0:
            return SizingDecision(
                quantity=0.0,
                requested_quantity=0.0,
                status="REJECTED",
                rationale="INVALID_EQUITY",
            )

        side = candidate.side
        if side is None:
            return SizingDecision(
                quantity=0.0,
                requested_quantity=0.0,
                status="REJECTED",
                rationale="ACTION_NOT_SIZABLE",
            )

        last_price = snapshot.last_price
        symbol = candidate.symbol

        # --- E. Base de sizing (sans multiplicateur) -----------------------
        if policy.target_notional is not None:
            requested_notional = policy.target_notional
        else:
            requested_notional = equity * policy.target_fraction_of_equity

        if requested_notional <= 0:
            return SizingDecision(
                quantity=0.0,
                requested_quantity=0.0,
                status="REJECTED",
                rationale="REQUESTED_NOTIONAL_NOT_POSITIVE",
            )

        requested_quantity = requested_notional / last_price

        if side is Side.BUY:
            return self._size_buy(
                policy=policy,
                portfolio=portfolio,
                equity=equity,
                symbol=symbol,
                last_price=last_price,
                requested_notional=requested_notional,
                requested_quantity=requested_quantity,
            )
        return self._size_sell(
            policy=policy,
            portfolio=portfolio,
            equity=equity,
            symbol=symbol,
            last_price=last_price,
            requested_notional=requested_notional,
            requested_quantity=requested_quantity,
        )

    # ------------------------------------------------------------------
    # F. Semantique BUY — ouvrir/augmenter une position LONGUE uniquement.
    # ------------------------------------------------------------------
    def _size_buy(
        self,
        *,
        policy: SizingPolicy,
        portfolio: PortfolioState,
        equity: float,
        symbol: str,
        last_price: float,
        requested_notional: float,
        requested_quantity: float,
    ) -> SizingDecision:
        # Drawdown : bloque tout NOUVEAU risque, jamais transforme en SELL.
        if (
            policy.max_drawdown_for_new_risk is not None
            and portfolio.drawdown > policy.max_drawdown_for_new_risk
        ):
            return SizingDecision(
                quantity=0.0,
                requested_quantity=requested_quantity,
                capped_by=("MAX_DRAWDOWN_FOR_NEW_RISK",),
                constraints=("MAX_DRAWDOWN_FOR_NEW_RISK",),
                status="REJECTED",
                rationale=(
                    "MAX_DRAWDOWN_FOR_NEW_RISK : drawdown actuel "
                    f"{portfolio.drawdown:.6f} depasse le seuil configure "
                    f"{policy.max_drawdown_for_new_risk:.6f} ; nouveau risque refuse."
                ),
            )

        current_symbol_value = portfolio.exposure_for(symbol) * equity
        current_gross_value = portfolio.gross_exposure * equity

        caps: Dict[str, float] = {}
        if policy.max_notional is not None:
            caps["MAX_NOTIONAL"] = policy.max_notional
        if policy.max_fraction_of_equity is not None:
            caps["MAX_FRACTION_OF_EQUITY"] = equity * policy.max_fraction_of_equity
        if policy.max_fraction_of_buying_power is not None:
            caps["MAX_FRACTION_OF_BUYING_POWER"] = (
                portfolio.account.buying_power * policy.max_fraction_of_buying_power
            )
        if policy.max_symbol_exposure is not None:
            caps["MAX_SYMBOL_EXPOSURE"] = max(
                0.0, policy.max_symbol_exposure * equity - current_symbol_value
            )
        if policy.max_portfolio_gross_exposure is not None:
            caps["MAX_PORTFOLIO_GROSS_EXPOSURE"] = max(
                0.0, policy.max_portfolio_gross_exposure * equity - current_gross_value
            )
        if policy.max_concentration is not None:
            # Conservateur : suppose que ce symbole pourrait devenir la plus
            # grosse position du portefeuille apres l'ajout propose.
            caps["MAX_CONCENTRATION"] = max(
                0.0, policy.max_concentration * equity - current_symbol_value
            )

        allowed_notional = requested_notional
        for cap_value in caps.values():
            if cap_value < allowed_notional:
                allowed_notional = cap_value

        capped_by: Tuple[str, ...] = tuple(
            sorted(name for name, value in caps.items() if value <= allowed_notional)
        ) if allowed_notional < requested_notional else ()

        if allowed_notional <= 0:
            return SizingDecision(
                quantity=0.0,
                requested_quantity=requested_quantity,
                capped_by=capped_by,
                constraints=capped_by,
                status="REJECTED",
                rationale=(
                    "BUY refuse : aucune notionnelle disponible sous les "
                    f"contraintes configurees {capped_by}."
                ),
            )

        raw_quantity = allowed_notional / last_price
        quantity = _normalize_down(raw_quantity, policy.quantity_increment)

        if quantity <= 0:
            return SizingDecision(
                quantity=0.0,
                requested_quantity=requested_quantity,
                capped_by=capped_by,
                constraints=capped_by,
                status="REJECTED",
                rationale="QUANTITY_ROUNDS_TO_ZERO",
            )

        notional = quantity * last_price
        fraction = notional / equity
        exposure_after = (current_symbol_value + notional) / equity
        rationale = (
            f"BUY {symbol}: quantite={quantity} notional={notional:.6f} "
            f"(demande={requested_quantity:.6f}, notional_demande={requested_notional:.6f})"
        )
        if capped_by:
            rationale += f" ; plafonne par {capped_by}"

        return SizingDecision(
            quantity=quantity,
            requested_quantity=requested_quantity,
            capped_by=capped_by,
            notional=notional,
            fraction=fraction,
            exposure_after=exposure_after,
            constraints=capped_by,
            rationale=rationale,
        )

    # ------------------------------------------------------------------
    # G. Semantique SELL — reduire une position LONGUE existante seulement.
    # V1 ne supporte pas l'ouverture/l'augmentation d'un SHORT.
    # ------------------------------------------------------------------
    def _size_sell(
        self,
        *,
        policy: SizingPolicy,
        portfolio: PortfolioState,
        equity: float,
        symbol: str,
        last_price: float,
        requested_notional: float,
        requested_quantity: float,
    ) -> SizingDecision:
        position = portfolio.position_for(symbol)
        if position is None or not position.is_long:
            return SizingDecision(
                quantity=0.0,
                requested_quantity=requested_quantity,
                status="REJECTED",
                rationale="SHORT_OPENING_UNSUPPORTED_V1 : aucune position longue existante a reduire.",
            )

        long_quantity = position.quantity
        open_sell_remaining = sum(
            order.remaining_quantity
            for order in portfolio.open_orders_for(symbol)
            if order.side is Side.SELL
        )
        reducible_quantity = max(0.0, long_quantity - open_sell_remaining)

        if reducible_quantity <= 0:
            return SizingDecision(
                quantity=0.0,
                requested_quantity=requested_quantity,
                capped_by=("REDUCIBLE_LONG_QUANTITY",),
                constraints=("REDUCIBLE_LONG_QUANTITY",),
                status="REJECTED",
                rationale=(
                    "SELL refuse : quantite reductible nulle (long="
                    f"{long_quantity}, deja engage en SELL={open_sell_remaining})."
                ),
            )

        # Drawdown/exposition/concentration ne bloquent JAMAIS une reduction
        # de risque : elles ne s'appliquent qu'a l'AJOUT de risque (BUY).
        raw_quantity = min(requested_quantity, reducible_quantity)
        quantity = _normalize_down(raw_quantity, policy.quantity_increment)

        capped_by: Tuple[str, ...] = (
            ("REDUCIBLE_LONG_QUANTITY",) if raw_quantity < requested_quantity else ()
        )

        if quantity <= 0:
            return SizingDecision(
                quantity=0.0,
                requested_quantity=requested_quantity,
                capped_by=capped_by,
                constraints=capped_by,
                status="REJECTED",
                rationale="QUANTITY_ROUNDS_TO_ZERO",
            )

        current_symbol_value = portfolio.exposure_for(symbol) * equity
        notional = quantity * last_price
        fraction = notional / equity
        exposure_after = max(0.0, (current_symbol_value - notional)) / equity
        rationale = (
            f"SELL {symbol}: quantite={quantity} notional={notional:.6f} "
            f"(demande={requested_quantity:.6f}, reductible={reducible_quantity})"
        )
        if capped_by:
            rationale += f" ; plafonne par {capped_by}"

        return SizingDecision(
            quantity=quantity,
            requested_quantity=requested_quantity,
            capped_by=capped_by,
            notional=notional,
            fraction=fraction,
            exposure_after=exposure_after,
            constraints=capped_by,
            rationale=rationale,
        )
