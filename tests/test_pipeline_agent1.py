# tests/test_pipeline_agent1.py
import json
import os

from utils.pdf_reader import extraire_texte_pdf
from agents.agent1_extraction import extraire_cv, extraire_offre

RACINE_PROJET = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHEMIN_CV = os.path.join(RACINE_PROJET, "data", "cv_samples", "cv_michel_scientist.pdf")
CHEMIN_OFFRE = os.path.join(RACINE_PROJET, "data", "offre_samples", "offre_data_scientist.pdf")

if __name__ == "__main__":
    print("--- Étape 1 : extraction du CV ---")
    texte_cv = extraire_texte_pdf(CHEMIN_CV)
    profil = extraire_cv(texte_cv)
    print(json.dumps(profil, indent=2, ensure_ascii=False))

    print("\n--- Étape 2 : extraction de l'offre ---")
    texte_offre = extraire_texte_pdf(CHEMIN_OFFRE)
    offre = extraire_offre(texte_offre)
    print(json.dumps(offre, indent=2, ensure_ascii=False))