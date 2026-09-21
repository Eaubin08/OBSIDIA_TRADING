"""
Obsidia Trading — ports (interfaces sortantes du systeme).

Un port decrit ce dont le moteur a besoin, jamais comment c'est fourni. Les
implementations vivent dans obsidia/adapters/ : le prototype historique en
PASS 2, Alpaca en PASS 3, sans que le moteur change d'une ligne.

Ce sont des Protocol structurels : une classe satisfait un port du seul fait
d'en avoir les methodes, sans heritage ni enregistrement.
"""

from domain.ports.broker import BrokerPort
from domain.ports.clock import ClockPort, FrozenClock, SystemClock
from domain.ports.market_data import MarketDataPort
from domain.ports.memory import MemoryPort
from domain.ports.news import NewsPort
from domain.ports.proof import ProofPort

__all__ = [
    "BrokerPort",
    "ClockPort",
    "FrozenClock",
    "SystemClock",
    "MarketDataPort",
    "MemoryPort",
    "NewsPort",
    "ProofPort",
]
