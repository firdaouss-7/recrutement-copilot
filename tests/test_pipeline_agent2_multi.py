import json
import logging
import os

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

from agents.agent2_matching import (
    calculer_matching,
    _parser_langue_requise,
    _normaliser_texte,
    _normaliser_niveau_langue,
    comparer_niveau_langue,
)


# ============================================================================
# CONFIGURATION
# ============================================================================

DOSSIER_FIXTURES = os.path.join(
    os.path.dirname(__file__),
    "fixtures",
    "agent2_v2"
)

CHEMIN_OFFRE = os.path.join(
    DOSSIER_FIXTURES,
    "offre.json"
)


# ============================================================================
# CHARGEMENT JSON
# ============================================================================

def charger_json(chemin):

    if not os.path.exists(chemin):
        raise FileNotFoundError(
            f"\nFichier introuvable : {chemin}\n"
            f"Vérifie que le fichier existe bien."
        )

    with open(
        chemin,
        encoding="utf-8"
    ) as fichier:

        return json.load(fichier)


# ============================================================================
# STYLES EXCEL
# ============================================================================

COULEUR_TITRE = "1F4E78"
COULEUR_SECTION = "D9EAD3"
COULEUR_ENTETE = "D9EAF7"

BORDURE_FINE = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin")
)


def styliser_titre(cellule):

    cellule.font = Font(
        bold=True,
        size=16
    )

    cellule.fill = PatternFill(
        "solid",
        fgColor=COULEUR_TITRE
    )

    cellule.alignment = Alignment(
        horizontal="center",
        vertical="center"
    )


def styliser_section(cellule):

    cellule.font = Font(
        bold=True,
        size=12
    )

    cellule.fill = PatternFill(
        "solid",
        fgColor=COULEUR_SECTION
    )

    cellule.alignment = Alignment(
        vertical="center"
    )


def styliser_entete(cellule):

    cellule.font = Font(
        bold=True
    )

    cellule.fill = PatternFill(
        "solid",
        fgColor=COULEUR_ENTETE
    )

    cellule.alignment = Alignment(
        horizontal="center",
        vertical="center",
        wrap_text=True
    )

    cellule.border = BORDURE_FINE


def styliser_cellule(cellule):

    cellule.alignment = Alignment(
        vertical="top",
        wrap_text=True
    )

    cellule.border = BORDURE_FINE


def ajuster_largeurs(feuille):

    for colonne in range(
        1,
        feuille.max_column + 1
    ):

        longueur_max = 0

        for ligne in range(
            1,
            feuille.max_row + 1
        ):

            valeur = feuille.cell(
                row=ligne,
                column=colonne
            ).value

            if valeur is not None:

                longueur = len(
                    str(valeur)
                )

                longueur_max = max(
                    longueur_max,
                    longueur
                )

        largeur = min(
            longueur_max + 3,
            45
        )

        feuille.column_dimensions[
            get_column_letter(colonne)
        ].width = max(
            largeur,
            12
        )


# ============================================================================
# UTILITAIRES
# ============================================================================

def trouver_detail_competence(
    diagnostic,
    competence
):

    details = diagnostic.get(
        "matching_competences_detail",
        []
    )

    for detail in details:

        if detail.get(
            "exigence_offre"
        ) == competence:

            return detail

    return None


def obtenir_texte_langues(
    profil_candidat
):

    langues = profil_candidat.get(
        "langues",
        []
    )

    valeurs = []

    for langue in langues:

        if isinstance(
            langue,
            dict
        ):

            nom = langue.get(
                "langue",
                ""
            )

            niveau = langue.get(
                "niveau",
                ""
            )

            if nom and niveau:

                valeurs.append(
                    f"{nom} ({niveau})"
                )

            elif nom:

                valeurs.append(
                    nom
                )

        else:

            valeurs.append(
                str(langue)
            )

    return " | ".join(
        valeurs
    )


def obtenir_texte_formations(
    profil_candidat
):

    formations = profil_candidat.get(
        "formations",
        []
    )

    valeurs = []

    for formation in formations:

        if isinstance(
            formation,
            dict
        ):

            intitule = formation.get(
                "intitule",
                ""
            )

            diplome = formation.get(
                "diplome",
                ""
            )

            if intitule and diplome:

                valeurs.append(
                    f"{intitule} ({diplome})"
                )

            elif intitule:

                valeurs.append(
                    intitule
                )

            elif diplome:

                valeurs.append(
                    diplome
                )

        else:

            valeurs.append(
                str(formation)
            )

    return " | ".join(
        valeurs
    )


# ============================================================================
# FEUILLE D'UN CV
# ============================================================================

def creer_feuille_cv(
    workbook,
    numero,
    profil_candidat,
    profil_offre,
    resultat
):

    nom_feuille = f"CV{numero}"

    feuille = workbook.create_sheet(
        nom_feuille
    )

    diagnostic = resultat.get(
        "_diagnostic",
        {}
    )

    # ========================================================================
    # TITRE
    # ========================================================================

    feuille.merge_cells(
        "A1:F1"
    )

    feuille["A1"] = (
        f"AGENT 2 — ANALYSE CV {numero}"
    )

    styliser_titre(
        feuille["A1"]
    )

    feuille.row_dimensions[1].height = 30

    # ========================================================================
    # INFORMATIONS GÉNÉRALES
    # ========================================================================

    feuille["A3"] = "Candidat"
    feuille["B3"] = (
        profil_candidat.get(
            "nom",
            f"CV {numero}"
        )
    )

    feuille["A4"] = "Poste"
    feuille["B4"] = profil_offre.get(
        "intitule_poste",
        ""
    )

    feuille["A5"] = "Score final"
    feuille["B5"] = resultat.get(
        "score_compatibilite"
    )

    feuille["C5"] = "Niveau"
    feuille["D5"] = resultat.get(
        "niveau_correspondance"
    )

    for cellule in [
        feuille["A3"],
        feuille["A4"],
        feuille["A5"],
        feuille["C5"]
    ]:

        cellule.font = Font(
            bold=True
        )

    # ========================================================================
    # 1. COMPÉTENCES
    # ========================================================================

    ligne = 7

    feuille.merge_cells(
        start_row=ligne,
        start_column=1,
        end_row=ligne,
        end_column=5
    )

    feuille.cell(
        row=ligne,
        column=1,
        value="1. COMPÉTENCES — MATCHING PAR EMBEDDINGS"
    )

    styliser_section(
        feuille.cell(
            row=ligne,
            column=1
        )
    )

    ligne += 1

    entetes_competences = [
        "Exigence de l'offre",
        "Meilleur match trouvé dans le CV",
        "Similarité",
        "Seuil",
        "Décision"
    ]

    for colonne, entete in enumerate(
        entetes_competences,
        start=1
    ):

        cellule = feuille.cell(
            row=ligne,
            column=colonne,
            value=entete
        )

        styliser_entete(
            cellule
        )

    ligne += 1

    competences = (
        profil_offre.get(
            "competences_techniques_requises",
            []
        )
        +
        profil_offre.get(
            "competences_transversales_requises",
            []
        )
    )

    for competence in competences:

        detail = trouver_detail_competence(
            diagnostic,
            competence
        )

        feuille.cell(
            row=ligne,
            column=1,
            value=competence
        )

        if detail is None:

            valeurs = [
                "Non disponible",
                "",
                "",
                "NON DISPONIBLE"
            ]

        else:

            similarite = detail.get(
                "similarite"
            )

            seuil = detail.get(
                "seuil"
            )

            couvert = detail.get(
                "couvert",
                False
            )

            valeurs = [

                detail.get(
                    "meilleur_match_cv",
                    ""
                ),

                similarite,

                seuil,

                (
                    "COUVERT"
                    if couvert
                    else "MANQUANT"
                )
            ]

        for decalage, valeur in enumerate(
            valeurs,
            start=2
        ):

            cellule = feuille.cell(
                row=ligne,
                column=decalage,
                value=valeur
            )

            styliser_cellule(
                cellule
            )

        # Similarité en pourcentage visuel
        cellule_similarite = feuille.cell(
            row=ligne,
            column=3
        )

        if isinstance(
            cellule_similarite.value,
            (int, float)
        ):

            cellule_similarite.number_format = (
                "0.0000"
            )

        cellule_seuil = feuille.cell(
            row=ligne,
            column=4
        )

        if isinstance(
            cellule_seuil.value,
            (int, float)
        ):

            cellule_seuil.number_format = (
                "0.00"
            )

        ligne += 1

    # ========================================================================
    # 2. EXPÉRIENCE
    # ========================================================================

    ligne += 1

    feuille.merge_cells(
        start_row=ligne,
        start_column=1,
        end_row=ligne,
        end_column=5
    )

    feuille.cell(
        row=ligne,
        column=1,
        value="2. EXPÉRIENCE"
    )

    styliser_section(
        feuille.cell(
            row=ligne,
            column=1
        )
    )

    ligne += 1

    entetes_experience = [
        "Exigence de l'offre",
        "Expérience du candidat",
        "Expérience requise",
        "Écart",
        "Décision"
    ]

    for colonne, entete in enumerate(
        entetes_experience,
        start=1
    ):

        cellule = feuille.cell(
            row=ligne,
            column=colonne,
            value=entete
        )

        styliser_entete(
            cellule
        )

    ligne += 1

    experience_candidat = diagnostic.get(
        "annees_experience_candidat"
    )

    experience_requise = diagnostic.get(
        "annees_experience_requises"
    )

    if (
        experience_candidat is None
        or experience_requise is None
    ):

        ecart = ""
        decision = "NON CALCULABLE"

    else:

        ecart = (
            experience_candidat
            - experience_requise
        )

        decision = (
            "OK"
            if experience_candidat >= experience_requise
            else "INSUFFISANT"
        )

    valeurs = [

        profil_offre.get(
            "experience_requise",
            ""
        ),

        (
            f"{experience_candidat} ans"
            if experience_candidat is not None
            else "Non calculable"
        ),

        (
            f"{experience_requise} ans"
            if experience_requise is not None
            else "Non calculable"
        ),

        (
            f"{ecart:+d} ans"
            if isinstance(
                ecart,
                int
            )
            else ""
        ),

        decision
    ]

    for colonne, valeur in enumerate(
        valeurs,
        start=1
    ):

        cellule = feuille.cell(
            row=ligne,
            column=colonne,
            value=valeur
        )

        styliser_cellule(
            cellule
        )

    ligne += 2

    # ========================================================================
    # 3. LANGUES (CORRIGÉ)
    # ========================================================================

    feuille.merge_cells(
        start_row=ligne,
        start_column=1,
        end_row=ligne,
        end_column=5
    )

    feuille.cell(
        row=ligne,
        column=1,
        value="3. LANGUES"
    )

    styliser_section(
        feuille.cell(
            row=ligne,
            column=1
        )
    )

    ligne += 1

    entetes_langues = [
        "Langue requise",
        "Langues du candidat",
        "Correspondance",
        "Niveau candidat",
        "Décision"
    ]

    for colonne, entete in enumerate(
        entetes_langues,
        start=1
    ):

        cellule = feuille.cell(
            row=ligne,
            column=colonne,
            value=entete
        )

        styliser_entete(
            cellule
        )

    ligne += 1

    langues_requises = profil_offre.get(
        "langues_requises",
        []
    )

    langues_candidat = profil_candidat.get(
        "langues",
        []
    )

    texte_langues_candidat = obtenir_texte_langues(
        profil_candidat
    )

    for langue_requise in langues_requises:

        langue_requise_str = str(
            langue_requise
        )

        # --------------------------------------------------------------
        # Même logique que calculer_couverture_langues (agent2_matching.py) :
        # on sépare le NOM de la langue du NIVEAU exigé, puis on compare
        # les niveaux sur une échelle ordinale tolérante, au lieu d'une
        # égalité stricte sur la chaîne complète
        # ("anglais professionnel" != "anglais").
        # --------------------------------------------------------------

        nom_requis, niveau_requis, niveau_non_reconnu = _parser_langue_requise(
            langue_requise
        )

        trouvee = None

        for langue in langues_candidat:

            if isinstance(langue, dict):

                nom_candidat = _normaliser_texte(
                    langue.get("langue", "")
                )

                if nom_candidat == nom_requis:
                    trouvee = langue
                    break

        if trouvee is None:

            niveau_affiche = ""
            correspondance = "Non"
            decision = "MANQUANT"

        else:

            niveau_affiche = trouvee.get(
                "niveau",
                ""
            )

            niveau_candidat_ord = _normaliser_niveau_langue(
                niveau_affiche
            )

            if niveau_non_reconnu:
                # L'offre exige un niveau qu'on n'a pas su interpréter :
                # score neutre, ni COUVERT ni MANQUANT franc.
                score = 0.5
            else:
                score = comparer_niveau_langue(
                    niveau_requis,
                    niveau_candidat_ord
                )

            correspondance = "Oui" if score > 0 else "Non"

            if score >= 1.0:
                decision = "COUVERT"
            elif score >= 0.5:
                decision = "PARTIEL"
            else:
                decision = "MANQUANT"

        valeurs = [

            langue_requise_str,

            texte_langues_candidat,

            correspondance,

            niveau_affiche,

            decision
        ]

        for colonne, valeur in enumerate(
            valeurs,
            start=1
        ):

            cellule = feuille.cell(
                row=ligne,
                column=colonne,
                value=valeur
            )

            styliser_cellule(
                cellule
            )

        ligne += 1

    # ========================================================================
    # 4. FORMATION
    # ========================================================================

    ligne += 1

    feuille.merge_cells(
        start_row=ligne,
        start_column=1,
        end_row=ligne,
        end_column=5
    )

    feuille.cell(
        row=ligne,
        column=1,
        value="4. FORMATION"
    )

    styliser_section(
        feuille.cell(
            row=ligne,
            column=1
        )
    )

    ligne += 1

    entetes_formation = [
        "Exigence de l'offre",
        "Formation du candidat",
        "Score dimension",
        "Correspondance",
        "Décision"
    ]

    for colonne, entete in enumerate(
        entetes_formation,
        start=1
    ):

        cellule = feuille.cell(
            row=ligne,
            column=colonne,
            value=entete
        )

        styliser_entete(
            cellule
        )

    ligne += 1

    niveau_etudes_requis = profil_offre.get(
        "niveau_etudes_requis",
        ""
    )

    score_formation = diagnostic.get(
        "scores_dimensions",
        {}
    ).get(
        "niveau_etudes"
    )

    if score_formation is None:

        decision_formation = "NON CALCULABLE"
        correspondance_formation = ""

    elif score_formation >= 1.0:

        decision_formation = "OK"
        correspondance_formation = "Complète"

    elif score_formation > 0:

        decision_formation = "PARTIEL"
        correspondance_formation = "Partielle"

    else:

        decision_formation = "INSUFFISANT"
        correspondance_formation = "Aucune"

    valeurs = [

        niveau_etudes_requis,

        obtenir_texte_formations(
            profil_candidat
        ),

        (
            f"{score_formation:.4f}"
            if score_formation is not None
            else "N/C"
        ),

        correspondance_formation,

        decision_formation
    ]

    for colonne, valeur in enumerate(
        valeurs,
        start=1
    ):

        cellule = feuille.cell(
            row=ligne,
            column=colonne,
            value=valeur
        )

        styliser_cellule(
            cellule
        )

    # ========================================================================
    # 5. RÉSULTAT FINAL
    # ========================================================================

    ligne += 2

    feuille.merge_cells(
        start_row=ligne,
        start_column=1,
        end_row=ligne,
        end_column=5
    )

    feuille.cell(
        row=ligne,
        column=1,
        value="5. RÉSULTAT FINAL"
    )

    styliser_section(
        feuille.cell(
            row=ligne,
            column=1
        )
    )

    ligne += 1

    resultats_finaux = [

        (
            "Score compatibilité",
            f"{resultat.get('score_compatibilite')}/100"
        ),

        (
            "Niveau",
            resultat.get(
                "niveau_correspondance",
                ""
            )
        ),

        (
            "Score brut avant cap",
            diagnostic.get(
                "score_brut_avant_cap"
            )
        ),

        (
            "Cap anti-inflation appliqué",
            diagnostic.get(
                "cap_anti_inflation_applique"
            )
        )
    ]

    for libelle, valeur in resultats_finaux:

        feuille.cell(
            row=ligne,
            column=1,
            value=libelle
        )

        feuille.cell(
            row=ligne,
            column=2,
            value=valeur
        )

        feuille.cell(
            row=ligne,
            column=1
        ).font = Font(
            bold=True
        )

        styliser_cellule(
            feuille.cell(
                row=ligne,
                column=1
            )
        )

        styliser_cellule(
            feuille.cell(
                row=ligne,
                column=2
            )
        )

        ligne += 1

    # ========================================================================
    # POINTS FORTS
    # ========================================================================

    ligne += 1

    feuille.merge_cells(
        start_row=ligne,
        start_column=1,
        end_row=ligne,
        end_column=5
    )

    feuille.cell(
        row=ligne,
        column=1,
        value="6. POINTS FORTS"
    )

    styliser_section(
        feuille.cell(
            row=ligne,
            column=1
        )
    )

    ligne += 1

    for point in resultat.get(
        "points_forts",
        []
    ):

        feuille.cell(
            row=ligne,
            column=1,
            value="✓"
        )

        feuille.cell(
            row=ligne,
            column=2,
            value=point
        )

        styliser_cellule(
            feuille.cell(
                row=ligne,
                column=1
            )
        )

        styliser_cellule(
            feuille.cell(
                row=ligne,
                column=2
            )
        )

        ligne += 1

    # ========================================================================
    # POINTS MANQUANTS
    # ========================================================================

    ligne += 1

    feuille.merge_cells(
        start_row=ligne,
        start_column=1,
        end_row=ligne,
        end_column=5
    )

    feuille.cell(
        row=ligne,
        column=1,
        value="7. POINTS MANQUANTS"
    )

    styliser_section(
        feuille.cell(
            row=ligne,
            column=1
        )
    )

    ligne += 1

    for point in resultat.get(
        "points_manquants",
        []
    ):

        feuille.cell(
            row=ligne,
            column=1,
            value="✗"
        )

        feuille.cell(
            row=ligne,
            column=2,
            value=point
        )

        styliser_cellule(
            feuille.cell(
                row=ligne,
                column=1
            )
        )

        styliser_cellule(
            feuille.cell(
                row=ligne,
                column=2
            )
        )

        ligne += 1

    # ========================================================================
    # EXPLICATION
    # ========================================================================

    ligne += 1

    feuille.merge_cells(
        start_row=ligne,
        start_column=1,
        end_row=ligne,
        end_column=5
    )

    feuille.cell(
        row=ligne,
        column=1,
        value="8. EXPLICATION"
    )

    styliser_section(
        feuille.cell(
            row=ligne,
            column=1
        )
    )

    ligne += 1

    feuille.merge_cells(
        start_row=ligne,
        start_column=1,
        end_row=ligne,
        end_column=5
    )

    feuille.cell(
        row=ligne,
        column=1,
        value=resultat.get(
            "explication",
            ""
        )
    )

    feuille.cell(
        row=ligne,
        column=1
    ).alignment = Alignment(
        wrap_text=True,
        vertical="top"
    )

    feuille.row_dimensions[
        ligne
    ].height = 80

    # ========================================================================
    # FIN
    # ========================================================================

    feuille.freeze_panes = "A9"

    feuille.sheet_view.showGridLines = False

    ajuster_largeurs(
        feuille
    )


# ============================================================================
# TEST MULTI-CV
# ============================================================================

def executer_test_multi():

    print("=" * 75)
    print("AGENT 2 — TEST MULTI-CV")
    print("=" * 75)

    # ========================================================================
    # 1. CHARGER L'OFFRE
    # ========================================================================

    profil_offre = charger_json(
        CHEMIN_OFFRE
    )

    print(
        "\n✓ Offre chargée :",
        profil_offre.get(
            "intitule_poste"
        )
    )

    # ========================================================================
    # 2. CHARGER LES 6 CV + CALCULER LE MATCHING
    # ========================================================================

    resultats = {}

    profils_candidats = {}

    for numero in range(1, 7):

        chemin_cv = os.path.join(
            DOSSIER_FIXTURES,
            f"cv{numero}.json"
        )

        print(
            f"\n--- Traitement CV {numero} ---"
        )

        profil_candidat = charger_json(
            chemin_cv
        )

        profils_candidats[
            f"cv{numero}"
        ] = profil_candidat

        resultat = calculer_matching(
            profil_candidat,
            profil_offre
        )

        resultats[
            f"cv{numero}"
        ] = resultat

        print(
            f"CV {numero} : "
            f"{resultat.get('score_compatibilite')}/100 "
            f"- "
            f"{resultat.get('niveau_correspondance')}"
        )

    # ========================================================================
    # 3. SAUVEGARDER RESULTATS JSON
    # ========================================================================

    chemin_resultats = os.path.join(
        DOSSIER_FIXTURES,
        "resultats_agent2.json"
    )

    with open(
        chemin_resultats,
        "w",
        encoding="utf-8"
    ) as fichier:

        json.dump(
            resultats,
            fichier,
            ensure_ascii=False,
            indent=2
        )

    print(
        "\n✓ resultats_agent2.json créé"
    )

    # ========================================================================
    # 4. CRÉER EXCEL
    # ========================================================================

    workbook = Workbook()

    # Supprimer la feuille vide créée par défaut
    feuille_defaut = workbook.active

    workbook.remove(
        feuille_defaut
    )

    # Créer CV1 → CV6
    for numero in range(1, 7):

        creer_feuille_cv(
            workbook=workbook,
            numero=numero,
            profil_candidat=profils_candidats[
                f"cv{numero}"
            ],
            profil_offre=profil_offre,
            resultat=resultats[
                f"cv{numero}"
            ]
        )

    # ========================================================================
    # 5. SAUVEGARDER EXCEL
    # ========================================================================

    chemin_excel = os.path.join(
        DOSSIER_FIXTURES,
        "tableau_comparaison_agent2.xlsx"
    )

    workbook.save(
        chemin_excel
    )

    print(
        "\n✓ tableau_comparaison_agent2.xlsx créé"
    )

    print(
        chemin_excel
    )

    # ========================================================================
    # 6. RÉSUMÉ TERMINAL
    # ========================================================================

    print("\n")
    print("=" * 75)
    print("RÉSUMÉ")
    print("=" * 75)

    for numero in range(1, 7):

        resultat = resultats[
            f"cv{numero}"
        ]

        print(
            f"CV {numero} : "
            f"{resultat.get('score_compatibilite')}/100 "
            f"- "
            f"{resultat.get('niveau_correspondance')}"
        )

    print("\n")
    print("=" * 75)
    print("TEST TERMINÉ")
    print("=" * 75)

    print(
        "\nFichiers générés :"
    )

    print(
        f"1. {chemin_resultats}"
    )

    print(
        f"2. {chemin_excel}"
    )

    return resultats


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(levelname)s - %(message)s"
    )

    executer_test_multi()