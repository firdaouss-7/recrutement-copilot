# tests/test_pipeline_agent2.py
#
# Version corrigée : n'appelle PLUS extraire_cv() / extraire_offre().
# Relit les fixtures JSON générées une seule fois par generer_fixtures.py.
# Résultat : Agent 2 reçoit toujours EXACTEMENT la même entrée
# -> le score de matching sera identique à chaque exécution.
#
# Prérequis : avoir lancé une fois `python -m tests.generer_fixtures`
#
# Commande pour lancer ce test :
#   python -m tests.test_pipeline_agent2

import json
import os

# TODO : adapte cet import au nom réel de ta fonction de matching
# dans agents/agent2_matching.py (ex: calculer_matching, matcher, etc.)
from agents.agent2_matching import calculer_matching

DOSSIER_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
CHEMIN_CANDIDAT = os.path.join(DOSSIER_FIXTURES, "profil_candidat.json")
CHEMIN_OFFRE = os.path.join(DOSSIER_FIXTURES, "profil_offre.json")


def charger_json(chemin):
    if not os.path.exists(chemin):
        raise FileNotFoundError(
            f"{chemin} introuvable. Lance d'abord :\n"
            f"  python -m tests.generer_fixtures"
        )
    with open(chemin, encoding="utf-8") as f:
        return json.load(f)


def executer_test():
    print("=" * 60)
    print("AGENT 1 : Extraction (LECTURE DEPUIS FIXTURES, pas d'appel LLM)")
    print("=" * 60)

    profil_candidat = charger_json(CHEMIN_CANDIDAT)
    profil_offre = charger_json(CHEMIN_OFFRE)

    print("CV chargé depuis fixture (stable)")
    print("Offre chargée depuis fixture (stable)")

    print("\n" + "=" * 60)
    print("AGENT 2 : Matching (Embeddings + Similarité)")
    print("=" * 60)

    resultat = calculer_matching(profil_candidat, profil_offre)

    print("\n" + "=" * 60)
    print("RÉSULTAT DU MATCHING")
    print("=" * 60)
    print(json.dumps(resultat, ensure_ascii=False, indent=2))

    print("\n" + "=" * 60)
    print("SYNTHÈSE")
    print("=" * 60)
    print(f"Score : {resultat['score_compatibilite']}/100")
    print(f"Niveau : {resultat['niveau_correspondance']}")
    print(f"Points forts : {len(resultat['points_forts'])}")
    print(f"Points manquants : {len(resultat['points_manquants'])}")

    return resultat


if __name__ == "__main__":
    executer_test()