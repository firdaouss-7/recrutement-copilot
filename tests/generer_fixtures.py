# tests/generer_fixtures.py
#
# À LANCER UNE SEULE FOIS (ou seulement si tu changes le CV / l'offre).
# Ce script appelle Agent 1 (LLM, non déterministe) et FIGE son résultat
# dans deux fichiers JSON. Tous les tests suivants d'Agent 2 (et Agent 3, 4)
# devront relire ces fichiers, jamais rappeler extraire_cv/extraire_offre.
#
# Commande pour lancer ce script :
#   python -m tests.generer_fixtures

import json
import os
from agents.agent1_extraction import extraire_cv, extraire_offre
from utils.pdf_reader import extraire_texte_pdf

# ---------------------------------------------------------------------
# Pas besoin de coller du texte à la main : on lit directement les PDF
# déjà présents dans data/, avec la même fonction extraire_texte_pdf()
# que ton pipeline utilise ailleurs (pdfplumber).
# Change ces deux chemins si tu veux figer un autre couple CV/offre.
# ---------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
CHEMIN_PDF_CV = os.path.join(BASE_DIR, "data", "cv_samples", "cv_michel_scientist.pdf")
CHEMIN_PDF_OFFRE = os.path.join(BASE_DIR, "data", "offre_samples", "offre_data_scientist.pdf")

DOSSIER_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
CHEMIN_CANDIDAT = os.path.join(DOSSIER_FIXTURES, "profil_candidat.json")
CHEMIN_OFFRE = os.path.join(DOSSIER_FIXTURES, "profil_offre.json")


def generer():
    os.makedirs(DOSSIER_FIXTURES, exist_ok=True)

    print(f"Lecture du PDF CV : {CHEMIN_PDF_CV}")
    texte_cv = extraire_texte_pdf(CHEMIN_PDF_CV)

    print(f"Lecture du PDF offre : {CHEMIN_PDF_OFFRE}")
    texte_offre = extraire_texte_pdf(CHEMIN_PDF_OFFRE)

    print("Extraction du CV (appel LLM, une seule fois)...")
    profil_candidat = extraire_cv(texte_cv)

    print("Extraction de l'offre (appel LLM, une seule fois)...")
    profil_offre = extraire_offre(texte_offre)

    with open(CHEMIN_CANDIDAT, "w", encoding="utf-8") as f:
        json.dump(profil_candidat, f, ensure_ascii=False, indent=2)

    with open(CHEMIN_OFFRE, "w", encoding="utf-8") as f:
        json.dump(profil_offre, f, ensure_ascii=False, indent=2)

    print(f"\nFixtures générées :")
    print(f"  - {CHEMIN_CANDIDAT}")
    print(f"  - {CHEMIN_OFFRE}")
    print("\nÀ partir de maintenant, test_pipeline_agent2.py doit relire")
    print("ces fichiers et ne plus jamais appeler extraire_cv/extraire_offre.")


if __name__ == "__main__":
    generer()