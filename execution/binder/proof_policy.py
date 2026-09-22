"""
Obsidia Trading — politique de preuve (F11).

Deux politiques coexistent explicitement :

    BEST_EFFORT  comportement herite (F3-F10) : le moteur tente de persister
                 chaque receipt, mais un cycle ne s'interrompt jamais si la
                 persistance echoue. C'est la valeur par defaut : aucun
                 appelant existant (Cockpit, demo, tests) ne casse.

    REQUIRED     pour le chemin gouverne critique. Ajoute une seule
                 verification supplementaire, AVANT tout appel broker : le
                 port de preuve doit etre joignable (`proof.last_hash()`).
                 S'il ne l'est pas, l'execution est refusee — aucun ordre ne
                 part. C'est la seule chose que REQUIRED empeche : demarrer
                 une action irreversible en sachant deja qu'on ne pourra
                 peut-etre pas en garder la preuve.

Ce que REQUIRED ne fait PAS : inventer une transaction atomique entre le
store de preuve (filesystem local) et le broker (API externe). Un ordre reel
peut toujours reussir alors que la preuve finale echoue a se persister
ensuite — c'est une limite reelle d'un systeme distribue, pas un defaut de
conception. Dans ce cas (les deux politiques, pas seulement REQUIRED),
`CycleOutcome.proof_outcome` porte la verite : jamais "rien ne s'est passe",
jamais "echec d'execution" si le broker a reellement pu accepter l'ordre.

Rappel : proof != authority. Cette politique ne change jamais qui autorise
une action (KX108 seul) ni qui l'execute (Binder seul, sous barriere
double). Elle decrit uniquement la rigueur exigee de la preuve.
"""
from __future__ import annotations

from enum import Enum


class ProofPolicy(str, Enum):
    """Politique de preuve appliquee par un CycleEngine."""

    BEST_EFFORT = "BEST_EFFORT"
    REQUIRED = "REQUIRED"


class ProofOutcome(str, Enum):
    """
    Etat honnete de la preuve d'un cycle — jamais une autorite, jamais une
    execution : seulement ce qu'on sait avoir pu (ou non) durablement
    enregistrer.
    """

    NOT_APPLICABLE = "NOT_APPLICABLE"
    """Aucun port de preuve configure (chaine en memoire uniquement, comme
    avant F7) : ni succes ni echec, la question ne se pose pas."""

    PROVEN = "PROVEN"
    """Le receipt a ete persiste avec succes, quelle que soit l'autorite."""

    PRE_EXECUTION_PROOF_FAILURE = "PRE_EXECUTION_PROOF_FAILURE"
    """Sous ProofPolicy.REQUIRED : le port de preuve etait injoignable avant
    tout appel broker. Aucune execution n'a ete tentee."""

    ABSTENTION_PROOF_INCOMPLETE = "ABSTENTION_PROOF_INCOMPLETE"
    """La persistance finale a echoue, mais ce cycle n'a touche aucun
    marche (HOLD/BLOCK/refuse) : aucun effet de bord externe en jeu."""

    EXECUTION_SUCCEEDED_PROOF_INCOMPLETE = "EXECUTION_SUCCEEDED_PROOF_INCOMPLETE"
    """Le broker a ete contacte et a potentiellement accepte l'ordre (voir
    `ExecutionResult.touched_the_market`), mais le receipt final n'a pas pu
    etre persiste durablement. L'action a peut-etre eu lieu ; la preuve
    qu'on peut en produire est incomplete. Ne jamais reduire cet etat a
    "echec" ni a "succes" : c'est une incertitude reelle, pas une erreur a
    masquer."""
