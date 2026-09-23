"""
RuntimeConfig — configuration produit immuable du Reference Runtime (P1-D).

Ne porte QUE de la configuration produit reelle. Les secrets/identifiants
broker restent geres exclusivement par `market.adapters.alpaca.alpaca_config
.AlpacaConfig.from_env()` (lecture `.env`/`os.environ`) : ce module ne les
duplique jamais et ne les recopie jamais dans un champ de `RuntimeConfig`.

Le Reference Runtime V1 est structurellement PAPER : aucun champ `mode` n'est
expose ici, et `ObsidiaTradingRuntime.build` n'assemble jamais de chemin LIVE
(voir `execution.binder.paper_execution.build_paper_cycle_engine`).

Aucun defaut financier n'est jamais implicite : `sizing_policy=None` reste
`None` (jamais une `SizingPolicy()` vide substituee), `calibration_pack=None`
reste `None` (jamais un pack estime a la volee).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from domain.calibration import CalibrationPack
from native.sizing.sizing_policy import SizingPolicy


class InvalidRuntimeConfig(ValueError):
    """La configuration runtime est structurellement invalide (echec a la construction)."""


@dataclass(frozen=True)
class RuntimeConfig:
    """
    Configuration produit du Reference Runtime.

    symbols               instruments suivis par ce runtime (non vide).
    order_ledger_path     chemin du journal d'ordres JSONL
                          (execution.binder.order_ledger_jsonl.JsonlOrderLedger).
    receipt_store_path    chemin du store de receipts JSONL
                          (proof.receipts.receipt_store.ReceiptStore). Si
                          `None`, le runtime tourne sans persistance de
                          receipts (chainage en memoire uniquement, comme
                          `CycleEngine` le fait deja quand `proof=None`) —
                          voir RuntimeStatus.receipt_store = UNAVAILABLE.
    kernel_url            URL du Kernel X-108 reel. Si `None`,
                          `RealKX108Client` retombe sur son propre defaut
                          (`OBSIDIA_KERNEL_URL` ou l'URL codee en dur) —
                          ce module n'invente aucune URL par defaut ici.
    sizing_policy         politique de dimensionnement explicite. Si absente,
                          le sizing reste fail-closed (P1-C).
    calibration_pack      pack de calibration explicite. Si absent, le
                          roster Native standard (non calibre) est utilise.
    """

    symbols: Tuple[str, ...]
    order_ledger_path: str
    receipt_store_path: Optional[str] = None
    kernel_url: Optional[str] = None
    sizing_policy: Optional[SizingPolicy] = None
    calibration_pack: Optional[CalibrationPack] = None

    def __post_init__(self) -> None:
        if not self.symbols:
            raise InvalidRuntimeConfig(
                "RuntimeConfig invalide : au moins un symbole doit etre configure."
            )
        if not self.order_ledger_path:
            raise InvalidRuntimeConfig(
                "RuntimeConfig invalide : order_ledger_path est obligatoire."
            )
