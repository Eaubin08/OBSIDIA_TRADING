"""
Governance Bridge — signal structurel LOCAL (chantier F5).

RAPPEL DE FRONTIERE (voir docs/B15_STRUCTURAL_SCORE_BOUNDARY.md) : la formule
portee ici est la version corrigee post-B15 d'agent-trad-main
(commit a6b271a, Option C). Elle produit un SIGNAL LOCAL — de la evidence
transportee jusqu'au Decision/receipt — jamais un verdict. Elle ne peut ni
produire ACT elle-meme, ni transformer un HOLD/BLOCK en ACT. Seul le vrai
Kernel X-108, via KX108Client, produit l'autorite.

Provenance :
  - triangle_mean / asymmetry_penalty / structural_score :
      COPY_AS_IS (formule) depuis agent-trad-main/agents/indicators.py
      (deja post-B15 : A_norm = A/(n-1), discount multiplicatif borne [0,1]).
  - build_coherence_matrix :
      ADAPT depuis agent-trad-main/core/guard_x108.py::_build_coherence_matrix.
      La source construisait W a partir de AgentVote.signal/.confidence (14
      agents du prototype). Ici, W est construit a partir de
      domain.proposal.AgentOutput.signal/.confidence (roster natif de 17
      agents, deja porte en F3) — meme algorithme, entree adaptee au
      vocabulaire canonique du domaine.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

from domain.proposal import AgentOutput


def build_coherence_matrix(outputs: Sequence[AgentOutput]) -> List[List[float]]:
    """
    Matrice de cohesion W entre sorties d'agents.

    W[i][j] = 1.0 sur la diagonale ; sinon, moyenne des confiances si les
    agents i et j emettent le meme signal (BUY/SELL/HOLD), 0.0 sinon.
    """
    n = len(outputs)
    W = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                W[i][j] = 1.0
            elif outputs[i].signal == outputs[j].signal:
                W[i][j] = (outputs[i].confidence + outputs[j].confidence) / 2.0
    return W


def triangle_mean(W: List[List[float]]) -> float:
    """Cohesion locale moyenne sur les triangles de la matrice W."""
    n = len(W)
    if n < 3:
        return 0.0
    triangles: List[float] = []
    theta = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            for k in range(j + 1, n):
                t = (W[i][j] + W[j][k] + W[k][i]) / 3.0
                if t >= theta:
                    triangles.append(t)
    return sum(triangles) / len(triangles) if triangles else 0.0


def asymmetry_penalty(W: List[List[float]]) -> float:
    """Penalite d'asymetrie (anti-domination d'un seul agent)."""
    degrees = [sum(row) for row in W]
    m = sum(degrees) / len(degrees)
    return sum(abs(d - m) for d in degrees) / len(degrees)


@dataclass(frozen=True)
class LocalStructuralSignal:
    """
    Decomposition du signal structurel local. Champs individuels exposes
    pour le contexte transmis a KX108 (T_mean/H_score/A_score) ; `S` est le
    score local post-B15, jamais le verdict.
    """

    T: float
    H: float
    A_norm: float
    S: float
    n_agents: int


def compute_local_structural_signal(
    outputs: Sequence[AgentOutput],
    alpha: float = 1.0,
    beta: float = 1.0,
    gamma: float = 0.5,
) -> LocalStructuralSignal:
    """
    Score structurel local normalise dans [0, 1] (formule post-B15, Option C).

    T = triangle_mean (cohesion locale)
    H = densite de connexion (proxy meso)
    A_norm = asymetrie normalisee sur [0, n-1] -> [0, 1]

    C'est un SIGNAL, pas un verdict : voir docstring de module.
    """
    if not outputs:
        return LocalStructuralSignal(T=0.0, H=0.0, A_norm=0.0, S=0.0, n_agents=0)

    W = build_coherence_matrix(outputs)
    n = len(W)
    T = triangle_mean(W)
    H = sum(sum(row) for row in W) / n**2
    A = asymmetry_penalty(W)
    A_norm = A / max(n - 1, 1)

    weighted_cohesion = (alpha * T + beta * H) / max(alpha + beta, 1e-12)
    discounted = weighted_cohesion * max(0.0, 1.0 - gamma * A_norm)
    S = max(0.0, min(1.0, discounted))

    return LocalStructuralSignal(T=T, H=H, A_norm=A_norm, S=S, n_agents=n)
