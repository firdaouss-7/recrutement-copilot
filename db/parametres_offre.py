# db/parametres_offre.py
#
# Preferences de matching/entretien laissees au recruteur, par offre.
# Chaque valeur par defaut reproduit exactement le comportement actuel
# du pipeline : une offre sans preference explicite se comporte comme
# avant l'introduction de ce module.

import json

from db.db import get_connexion


PARAMETRES_PAR_DEFAUT = {
    "plafond_anti_inflation_actif": True,       # etape 1 : interrupteur
    "plafond_anti_inflation_niveau": "standard", # etape 1bis : "tolerant" | "standard" | "strict"    # etape 1
    "score_minimal_affichage": None,            # etape 2 (None = pas de filtre)
    "nb_questions_mode": "auto",                # etape 3 ("auto" | "manuel")
    "nb_questions_manuel": None,                # etape 3 (utilise si mode = "manuel")

    # etape 4 : couverture des langues -- 3 situations, chacune reglable
    # independamment sur "acquise" | "partielle" | "manquante" (voir
    # NIVEAUX_LANGUE_CHOIX / SCORES_NIVEAU_LANGUE ci-dessous). Les valeurs
    # par defaut ci-dessous reproduisent exactement le comportement
    # d'origine du code (comparer_niveau_langue avant ce reglage).
    # NB : le cas "langue totalement absente du CV" (jamais mentionnee)
    # reste volontairement fixe a "manquante", non configurable -- ce
    # n'est pas une question de niveau insuffisant, la competence
    # n'apparait juste pas dans le profil.
    "langue_niveau_non_precise": "manquante",   # etape 4a : langue mentionnee mais niveau illisible/absent
    "langue_ecart_1_niveau": "partielle",       # etape 4b : ecart d'1 niveau (ex. candidat B1, poste exige B2)
    "langue_ecart_2_niveaux_plus": "manquante", # etape 4c : ecart de 2 niveaux ou plus

    # etape 4bis : couverture de la formation -- meme principe que les
    # langues, 3 situations reglables independamment. Les valeurs par
    # defaut reproduisent le comportement d'origine (comparer_niveau_etudes
    # avant ce reglage). Comme pour les langues, le cas "aucune formation
    # du tout listee sur le CV" reste fixe a "manquante", non
    # configurable -- seul le cas "formation listee mais diplome non
    # reconnu par le dictionnaire" (intitule atypique, diplome etranger...)
    # devient reglable, pour ne pas penaliser a tort ces profils.
    "formation_diplome_non_reconnu": "manquante",  # etape 4bis-a : formation listee, diplome non reconnu
    "formation_ecart_1_niveau": "partielle",        # etape 4bis-b : ecart d'1 niveau (ex. Licence vs Master exige)
    "formation_ecart_2_niveaux_plus": "manquante",  # etape 4bis-c : ecart de 2 niveaux ou plus

    "severite_matching": "standard",            # etape 5 ("souple" | "standard" | "strict")
    "ponderation_dimensions": None,             # etape 6 (None = valeurs par defaut ci-dessous, voir POIDS_PONDERATION_DEFAUT)
}

# etape 6 : poids relatifs par defaut des 4 dimensions du matching.
# Ce sont EXACTEMENT les valeurs d'origine de POIDS_INITIAUX
# (agents/agent2_matching.py) : une offre sans preference explicite
# donne un score identique a avant l'introduction de ce reglage. Ce
# sont des poids RELATIFS, pas des pourcentages devant sommer a 100 :
# ils sont toujours renormalises au calcul (redistribuer_poids), donc
# n'importe quelle combinaison de curseurs 0-100 choisie par le
# recruteur reste valide sans contrainte de somme.
POIDS_PONDERATION_DEFAUT = {
    "competences": 35,
    "langues": 15,
    "niveau_etudes": 15,
    "experience": 25,
}
# Correspondance entre le niveau choisi par le recruteur et les 2 valeurs
# techniques utilisees par le calcul (jamais exposees telles quelles au
# recruteur). "standard" reproduit exactement les valeurs d'origine du code.
NIVEAUX_PLAFOND_ANTI_INFLATION = {
    "tolerant": {"seuil_couverture": 0.25, "score_max": 55},
    "standard": {"seuil_couverture": 0.35, "score_max": 50},
    "strict":   {"seuil_couverture": 0.45, "score_max": 40},
}

# etape 4 / 4bis : les 3 choix possibles pour chaque situation de
# couverture (langue ou formation), et leur traduction en score
# numerique. Reutilise a l'identique pour les langues et la formation
# -- meme echelle Acquise/Partielle/Manquante dans les 2 cas. Ce score
# n'est JAMAIS montre au recruteur -- l'interface n'affiche que les 3
# mots, le mapping vers 1.0/0.5/0.0 reste un detail interne.
NIVEAUX_LANGUE_CHOIX = ["acquise", "partielle", "manquante"]

SCORES_NIVEAU_LANGUE = {
    "acquise": 1.0,
    "partielle": 0.5,
    "manquante": 0.0,
}


def resoudre_reglages_langues(parametres: dict) -> dict:
    """Traduit les 3 choix du recruteur (acquise/partielle/manquante),
    stockes pour chaque situation, en scores numeriques utilises par
    calculer_couverture_langues / comparer_niveau_langue. Retombe sur
    le choix par defaut de la situation si la valeur stockee est
    absente ou invalide.

    Retourne :
        {
            "score_niveau_non_precise":     float,  # etape 4a
            "score_ecart_1_niveau":         float,  # etape 4b
            "score_ecart_2_niveaux_ou_plus": float, # etape 4c
        }
    """

    def _score(cle: str, defaut: str) -> float:
        choix = parametres.get(cle, defaut)
        return SCORES_NIVEAU_LANGUE.get(choix, SCORES_NIVEAU_LANGUE[defaut])

    return {
        "score_niveau_non_precise": _score(
            "langue_niveau_non_precise",
            PARAMETRES_PAR_DEFAUT["langue_niveau_non_precise"],
        ),
        "score_ecart_1_niveau": _score(
            "langue_ecart_1_niveau",
            PARAMETRES_PAR_DEFAUT["langue_ecart_1_niveau"],
        ),
        "score_ecart_2_niveaux_ou_plus": _score(
            "langue_ecart_2_niveaux_plus",
            PARAMETRES_PAR_DEFAUT["langue_ecart_2_niveaux_plus"],
        ),
    }


def resoudre_reglages_formation(parametres: dict) -> dict:
    """Equivalent de resoudre_reglages_langues, pour la couverture de
    la formation. Traduit les 3 choix du recruteur en scores numeriques
    utilises par comparer_niveau_etudes. Retombe sur le choix par
    defaut de la situation si la valeur stockee est absente ou
    invalide.

    Retourne :
        {
            "score_diplome_non_reconnu":    float,  # etape 4bis-a
            "score_ecart_1_niveau":         float,  # etape 4bis-b
            "score_ecart_2_niveaux_ou_plus": float, # etape 4bis-c
        }
    """

    def _score(cle: str, defaut: str) -> float:
        choix = parametres.get(cle, defaut)
        return SCORES_NIVEAU_LANGUE.get(choix, SCORES_NIVEAU_LANGUE[defaut])

    return {
        "score_diplome_non_reconnu": _score(
            "formation_diplome_non_reconnu",
            PARAMETRES_PAR_DEFAUT["formation_diplome_non_reconnu"],
        ),
        "score_ecart_1_niveau": _score(
            "formation_ecart_1_niveau",
            PARAMETRES_PAR_DEFAUT["formation_ecart_1_niveau"],
        ),
        "score_ecart_2_niveaux_ou_plus": _score(
            "formation_ecart_2_niveaux_plus",
            PARAMETRES_PAR_DEFAUT["formation_ecart_2_niveaux_plus"],
        ),
    }


def resoudre_plafond_anti_inflation(parametres: dict) -> dict:
    """Traduit le niveau choisi par le recruteur (tolerant/standard/strict)
    en valeurs numeriques (seuil_couverture, score_max) utilisees par
    appliquer_cap_anti_inflation. Retombe sur "standard" si le niveau
    stocke est invalide ou absent."""

    niveau = parametres.get("plafond_anti_inflation_niveau", "standard")
    return NIVEAUX_PLAFOND_ANTI_INFLATION.get(
        niveau, NIVEAUX_PLAFOND_ANTI_INFLATION["standard"]
    )


def resoudre_ponderation(parametres: dict) -> dict:
    """Retourne les poids relatifs des 4 dimensions du matching a
    utiliser pour cette offre. Si le recruteur n'a rien choisi
    (ponderation_dimensions absent/None), retombe sur
    POIDS_PONDERATION_DEFAUT (= comportement d'origine, inchange).

    La fusion avec POIDS_PONDERATION_DEFAUT garantit qu'une dimension
    manquante dans les parametres stockes (ex. ancienne offre, ou cle
    ajoutee plus tard) a quand meme une valeur par defaut plutot que
    de disparaitre silencieusement du calcul."""

    ponderation_stockee = parametres.get("ponderation_dimensions") or {}
    return {**POIDS_PONDERATION_DEFAUT, **ponderation_stockee}


def obtenir_parametres_offre(offre_id: int) -> dict:
    """Retourne les parametres de l'offre, fusionnes avec les valeurs par
    defaut. La fusion garantit qu'une cle ajoutee plus tard (nouvelle
    etape) existe meme sur une offre creee avant son ajout."""

    conn = get_connexion()
    row = conn.execute(
        "SELECT parametres_matching FROM offres WHERE id = ?", (offre_id,)
    ).fetchone()
    conn.close()

    parametres_stockes = {}
    if row and row["parametres_matching"]:
        parametres_stockes = json.loads(row["parametres_matching"])

    return {**PARAMETRES_PAR_DEFAUT, **parametres_stockes}


def mettre_a_jour_parametres_offre(offre_id: int, nouveaux_parametres: dict) -> None:
    """Met a jour uniquement les cles fournies dans nouveaux_parametres,
    sans ecraser les autres preferences deja enregistrees pour l'offre."""

    parametres_actuels = obtenir_parametres_offre(offre_id)
    parametres_actuels.update(nouveaux_parametres)

    conn = get_connexion()
    conn.execute(
        "UPDATE offres SET parametres_matching = ? WHERE id = ?",
        (json.dumps(parametres_actuels, ensure_ascii=False), offre_id),
    )
    conn.commit()
    conn.close()