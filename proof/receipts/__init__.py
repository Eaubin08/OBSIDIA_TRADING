"""
Re-export du mecanisme de preuve chaine.

Le code reel (CycleReceipt, Decision, canonical_json, verify_chain, GENESIS_HASH)
vit dans domain/receipt.py (COPY_AS_IS depuis agent-trad-main), pas ici. La preuve
fait partie du vocabulaire du domaine dans le code source original (obsidia/domain/receipt.py) ;
on ne casse pas cette dependance interne (domain/order_ledger.py et domain/memory.py
importent canonical_json depuis le meme module). Ce module ne fait que reexposer
ce contenu sous l'emplacement logique proof/receipts/ demande par l'architecture cible.

Voir docs/MIGRATION_PROVENANCE.md pour la justification de ce choix.
"""
from domain.receipt import GENESIS_HASH, CycleReceipt, Decision, canonical_json, verify_chain  # noqa: F401

# F7 : store/verify/replay reels vivent dans des modules dedies (receipt_store.py,
# receipt_verify.py, replay.py) plutot que dans ce __init__ : ce sont des classes
# avec etat/IO (fichier JSONL), pas du simple vocabulaire de type comme ci-dessus.
from proof.receipts.receipt_store import ReceiptStore, StoredCycleReceipt  # noqa: F401
from proof.receipts.receipt_verify import IntegrityReport, IntegrityStatus, ReceiptChainVerifier  # noqa: F401
from proof.receipts.replay import (  # noqa: F401
    AuditReplayResult,
    DeterministicReplayResult,
    DeterministicReplayVerdict,
    ReplayEngine,
)
