import os
from utils.pdf_reader import extraire_texte_pdf

RACINE_PROJET = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHEMIN_CV_TEST = os.path.join(RACINE_PROJET, "data", "cv_samples", "cv_michel_scientist.pdf")
CHEMIN_OFFRE_TEST = os.path.join(RACINE_PROJET, "data", "offre_samples", "offre_data_scientist.pdf")

if __name__ == "__main__":
    texte_cv = extraire_texte_pdf(CHEMIN_CV_TEST)
    print(f"CV : {len(texte_cv)} caractères extraits.")

    texte_offre = extraire_texte_pdf(CHEMIN_OFFRE_TEST)
    print(f"Offre : {len(texte_offre)} caractères extraits.")