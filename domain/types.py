"""
Obsidia Trading — vocabulaire canonique du domaine.

Ce module ne contient que des types de valeur. Aucune dependance vers un
broker, un feed ou une UI : c'est le socle partage par toutes les couches.

Point de vocabulaire (chantier §12) : l'autorite decisionnelle s'exprime en
ACT / HOLD / BLOCK. Le prototype historique parle ALLOW / HOLD / BLOCK ;
`Authority.from_legacy` assure la traduction sans casser l'existant.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple


class Authority(str, Enum):
    """Verdict de X-108. Seul ACT autorise une action irreversible."""

    ACT = "ACT"
    HOLD = "HOLD"
    BLOCK = "BLOCK"

    @classmethod
    def from_legacy(cls, value: str) -> "Authority":
        """Traduit la semantique historique (ALLOW/HOLD/BLOCK) vers ACT/HOLD/BLOCK."""
        normalized = str(value).strip().upper()
        if normalized in ("ALLOW", "ACT"):
            return cls.ACT
        if normalized == "HOLD":
            return cls.HOLD
        if normalized == "BLOCK":
            return cls.BLOCK
        raise ValueError(f"autorite inconnue: {value!r}")

    def to_legacy(self) -> str:
        """Retour vers la semantique historique, pour les composants non migres."""
        return "ALLOW" if self is Authority.ACT else self.value

    @property
    def authorizes_irreversible_action(self) -> bool:
        return self is Authority.ACT


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

    @property
    def opposite(self) -> "Side":
        return Side.SELL if self is Side.BUY else Side.BUY


class ActionKind(str, Enum):
    """
    Espace des actions envisageables (chantier §8).

    Une proposition n'est pas un ordre : elle nomme ce que le systeme envisage.
    NO_ACTION et WAIT sont des reponses valides et portent autant de sens
    qu'un BUY.
    """

    BUY = "BUY"
    SELL = "SELL"
    ADD = "ADD"
    REDUCE = "REDUCE"
    CLOSE = "CLOSE"
    KEEP = "KEEP"
    MODIFY_ORDER = "MODIFY_ORDER"
    CANCEL_ORDER = "CANCEL_ORDER"
    WAIT = "WAIT"
    NO_ACTION = "NO_ACTION"

    @property
    def is_irreversible(self) -> bool:
        """
        Une action irreversible modifie l'exterieur et ne peut pas etre
        annulee par simple decision interne. Elle exige ACT.
        """
        return self in (
            ActionKind.BUY,
            ActionKind.SELL,
            ActionKind.ADD,
            ActionKind.REDUCE,
            ActionKind.CLOSE,
            ActionKind.MODIFY_ORDER,
            ActionKind.CANCEL_ORDER,
        )

    @property
    def side(self) -> Optional[Side]:
        """Direction broker impliquee, ou None si l'action n'en porte pas."""
        if self in (ActionKind.BUY, ActionKind.ADD):
            return Side.BUY
        if self in (ActionKind.SELL, ActionKind.REDUCE, ActionKind.CLOSE):
            return Side.SELL
        return None


class AssetClass(str, Enum):
    EQUITY = "EQUITY"
    CRYPTO = "CRYPTO"
    OPTION = "OPTION"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"
    TRAILING_STOP = "TRAILING_STOP"


class TimeInForce(str, Enum):
    DAY = "DAY"
    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"


class OrderStatus(str, Enum):
    """Cycle de vie d'un ordre cote broker."""

    PENDING_SUBMIT = "PENDING_SUBMIT"
    ACCEPTED = "ACCEPTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"

    @property
    def is_terminal(self) -> bool:
        return self in (
            OrderStatus.FILLED,
            OrderStatus.CANCELED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        )

    @property
    def is_open(self) -> bool:
        return self in (
            OrderStatus.PENDING_SUBMIT,
            OrderStatus.ACCEPTED,
            OrderStatus.PARTIALLY_FILLED,
        )


class Mode(str, Enum):
    """
    Mode d'execution. PAPER et LIVE traversent le meme pipeline (chantier §2) ;
    seule la destination broker change. SIM designe un marche synthetique local,
    utilise pour les tests et les scenarios reproductibles.
    """

    SIM = "SIM"
    PAPER = "PAPER"
    LIVE = "LIVE"

    @property
    def touches_real_broker(self) -> bool:
        return self in (Mode.PAPER, Mode.LIVE)


class DataQuality(str, Enum):
    """
    Qualite d'une donnee du domaine.

    Chantier §30 : une donnee essentielle inconnue ne doit jamais etre
    silencieusement inventee. Toute valeur absente est portee par
    DataQuality.MISSING plutot que par un defaut arbitraire.
    """

    LIVE = "LIVE"
    DELAYED = "DELAYED"
    CACHED = "CACHED"
    SYNTHETIC = "SYNTHETIC"
    STALE = "STALE"
    MISSING = "MISSING"

    @property
    def is_trustworthy_for_irreversible_action(self) -> bool:
        return self in (DataQuality.LIVE, DataQuality.DELAYED)


@dataclass(frozen=True)
class Provenance:
    """
    D'ou vient une donnee, quand, et dans quel etat de confiance.

    Attachee a chaque bloc du TradingDomainState pour que le receipt puisse
    repondre a « sur quoi le systeme s'est-il appuye pour decider ».
    """

    source: str
    fetched_at: float
    quality: DataQuality = DataQuality.LIVE
    mode: Mode = Mode.SIM
    degraded_reasons: Tuple[str, ...] = field(default_factory=tuple)

    def degraded(self, reason: str, quality: DataQuality) -> "Provenance":
        """Retourne une provenance derivee marquant une degradation."""
        return Provenance(
            source=self.source,
            fetched_at=self.fetched_at,
            quality=quality,
            mode=self.mode,
            degraded_reasons=self.degraded_reasons + (reason,),
        )

    @property
    def is_degraded(self) -> bool:
        return bool(self.degraded_reasons) or self.quality in (
            DataQuality.STALE,
            DataQuality.MISSING,
            DataQuality.SYNTHETIC,
        )

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "fetched_at": self.fetched_at,
            "quality": self.quality.value,
            "mode": self.mode.value,
            "degraded_reasons": list(self.degraded_reasons),
        }
