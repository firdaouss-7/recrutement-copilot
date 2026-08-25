import json
import os

from utils.pdf_reader import extraire_texte_pdf
from agents.agent1_extraction import extraire_cv, extraire_offre


RACINE_PROJET = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DOSSIER_PDF = os.path.join(
    RACINE_PROJET,
    "data",
    "test_agent2_v2"
)

DOSSIER_FIXTURES = os.path.join(
    RACINE_PROJET,
    "tests",
    "fixtures",
    "agent2_v2"
)


def sauvegarder_json(chemin, donnees):
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(
            donnees,
            f,
            ensure_ascii=False,
            indent=2
        )


def generer_fixtures():
    os.makedirs(DOSSIER_FIXTURES, exist_ok=True)

    # ============================================================
    # 1. OFFRE
    # ============================================================

    chemin_offre = os.path.join(DOSSIER_PDF, "offre.pdf")

    print("=" * 70)
    print("AGENT 1 — EXTRACTION DE L'OFFRE")
    print("=" * 70)

    texte_offre = extraire_texte_pdf(chemin_offre)
    profil_offre = extraire_offre(texte_offre)

    chemin_offre_json = os.path.join(
        DOSSIER_FIXTURES,
        "offre.json"
    )

    sauvegarder_json(chemin_offre_json, profil_offre)

    print(f"✓ Offre extraite → {chemin_offre_json}")


    # ============================================================
    # 2. LES 6 CV
    # ============================================================

    for numero in range(1, 7):

        nom_pdf = f"cv{numero}.pdf"
        chemin_cv = os.path.join(DOSSIER_PDF, nom_pdf)

        print("\n" + "=" * 70)
        print(f"AGENT 1 — EXTRACTION CV {numero}")
        print("=" * 70)

        if not os.path.exists(chemin_cv):
            raise FileNotFoundError(
                f"CV introuvable : {chemin_cv}"
            )

        texte_cv = extraire_texte_pdf(chemin_cv)
        profil_cv = extraire_cv(texte_cv)

        chemin_cv_json = os.path.join(
            DOSSIER_FIXTURES,
            f"cv{numero}.json"
        )

        sauvegarder_json(chemin_cv_json, profil_cv)

        print(f"✓ CV {numero} extrait → {chemin_cv_json}")


    print("\n" + "=" * 70)
    print("EXTRACTION TERMINÉE")
    print("=" * 70)

    print(f"\nFixtures disponibles dans :")
    print(DOSSIER_FIXTURES)


if __name__ == "__main__":
    generer_fixtures()