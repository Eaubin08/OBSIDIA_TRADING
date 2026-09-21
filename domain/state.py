"""
Obsidia Trading — TradingDomainState (chantier §5).

Structure canonique du domaine. C'est la frontiere : au-dessus, le monde
exterieur (Alpaca, Binance, un mock) ; en dessous, le Kernel et les agents,
qui ne connaissent que ce type.

Regle du chantier §13 : les APIs du fournisseur ne contaminent jamais le
Kernel. Un adapter traduit le monde vers cet objet, et rien d'autre ne le
fait.

Regle du chantier §30 : ce qui n'est pas connu vaut None et se lit dans la
provenance. Aucune valeur n'est inventee pour combler un trou.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from domain.market import MarketContext, MarketSnapshot
from domain.portfolio import PortfolioState
from domain.proposal import Opportunity
from domain.types import DataQuality, Mode


@dataclass(frozen=True)
class TradingDomainState:
    """
    Etat complet du monde tel que le systeme le percoit a un instant donne.

    Immuable par construction : un cycle observe un etat, il ne le mute pas.
    Le cycle suivant en observe un nouveau. C'est ce qui rend le rejeu
    possible (chantier §25).
    """

    cycle_id: str
    observed_at: float
    mode: Mode
    market: Dict[str, MarketSnapshot] = field(default_factory=dict)
    portfolio: Optional[PortfolioState] = None
    context: Optional[MarketContext] = None
    opportunities: Tuple[Opportunity, ...] = field(default_factory=tuple)
    degraded_reasons: Tuple[str, ...] = field(default_factory=tuple)

    # ── Acces ────────────────────────────────────────────────────────────

    def snapshot(self, symbol: str) -> Optional[MarketSnapshot]:
        return self.market.get(symbol)

    @property
    def symbols(self) -> Tuple[str, ...]:
        return tuple(sorted(self.market))

    # ── Sante de l'etat ──────────────────────────────────────────────────

    @property
    def is_degraded(self) -> bool:
        """Vrai des qu'une partie de l'etat est incomplete ou peu fiable."""
        if self.degraded_reasons:
            return True
        if self.portfolio is None:
            return True
        if any(s.provenance.is_degraded for s in self.market.values()):
            return True
        return self.portfolio.account.provenance.is_degraded

    def can_support_irreversible_action(self, symbol: str) -> Tuple[bool, str]:
        """
        Un etat degrade ne doit pas porter une action irreversible.

        Retourne (autorise, raison). La raison est destinee au receipt : le
        systeme doit pouvoir expliquer pourquoi il s'est abstenu, et non
        seulement qu'il s'est abstenu.
        """
        if self.portfolio is None:
            return False, "etat portefeuille inconnu"
        if self.portfolio.account.trading_blocked:
            return False, "compte bloque par le broker"

        snapshot = self.snapshot(symbol)
        if snapshot is None:
            return False, f"aucune donnee de marche pour {symbol}"
        if not snapshot.tradable:
            return False, f"{symbol} non negociable"
        if snapshot.market_open is False:
            return False, f"marche ferme pour {symbol}"
        if snapshot.last_price <= 0:
            return False, f"prix invalide pour {symbol}"
        if not self._quality_is_acceptable(snapshot.provenance.quality):
            return False, (
                f"qualite de donnee insuffisante pour {symbol} "
                f"({snapshot.provenance.quality.value}) en mode {self.mode.value}"
            )
        return True, "etat suffisant"

    def _quality_is_acceptable(self, quality: DataQuality) -> bool:
        """
        Une donnee synthetique est la source legitime en mode SIM : c'est le
        marche simule lui-meme. Elle devient au contraire disqualifiante des
        que de l'argent reel est en jeu, ou meme du papier — en PAPER et en
        LIVE, agir sur des donnees inventees n'aurait aucun sens.
        """
        if self.mode is Mode.SIM:
            return quality is not DataQuality.MISSING
        return quality.is_trustworthy_for_irreversible_action

    # ── Empreinte ────────────────────────────────────────────────────────

    def fingerprint(self) -> str:
        """
        Empreinte SHA-256 de l'etat observe, hors horodatage.

        Deux observations identiques du monde produisent la meme empreinte,
        meme a des instants differents : c'est ce qui permet de verifier la
        propriete « meme etat -> meme decision » du chantier §25.
        """
        payload = {
            "mode": self.mode.value,
            "market": {s: snap.as_dict() for s, snap in sorted(self.market.items())},
            "portfolio": self.portfolio.as_dict() if self.portfolio else None,
            "opportunities": [o.as_dict() for o in self.opportunities],
        }
        # L'horodatage et la fraicheur ne font pas partie de l'identite de
        # l'etat : deux rejeux du meme monde doivent coincider.
        for snapshot in payload["market"].values():
            snapshot.get("provenance", {}).pop("fetched_at", None)
        if payload["portfolio"]:
            payload["portfolio"]["account"].get("provenance", {}).pop("fetched_at", None)

        raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def as_dict(self) -> dict:
        return {
            "cycle_id": self.cycle_id,
            "observed_at": self.observed_at,
            "mode": self.mode.value,
            "symbols": list(self.symbols),
            "market": {s: snap.as_dict() for s, snap in sorted(self.market.items())},
            "portfolio": self.portfolio.as_dict() if self.portfolio else None,
            "context": self.context.as_dict() if self.context else None,
            "opportunities": [o.as_dict() for o in self.opportunities],
            "is_degraded": self.is_degraded,
            "degraded_reasons": list(self.degraded_reasons),
            "state_fingerprint": self.fingerprint(),
        }

    def with_opportunities(
        self, opportunities: Tuple[Opportunity, ...]
    ) -> "TradingDomainState":
        """Derive un nouvel etat enrichi des opportunites decouvertes."""
        return TradingDomainState(
            cycle_id=self.cycle_id,
            observed_at=self.observed_at,
            mode=self.mode,
            market=self.market,
            portfolio=self.portfolio,
            context=self.context,
            opportunities=opportunities,
            degraded_reasons=self.degraded_reasons,
        )

    def degraded(self, reason: str) -> "TradingDomainState":
        """Derive un nouvel etat portant une degradation supplementaire."""
        return TradingDomainState(
            cycle_id=self.cycle_id,
            observed_at=self.observed_at,
            mode=self.mode,
            market=self.market,
            portfolio=self.portfolio,
            context=self.context,
            opportunities=self.opportunities,
            degraded_reasons=self.degraded_reasons + (reason,),
        )
