# graph/pipeline.py
#
# Orchestration LangGraph du pipeline : Agent 1 (extraction) -> Agent 2
# (matching). Un etat partage (PipelineState) circule entre les noeuds ;
# chaque noeud appelle une fonction d'agent EXISTANTE, sans la modifier,
# et sauvegarde son resultat en base au passage.
#
# Ce module traite UN SEUL candidat a la fois (le pipeline est rejoue
# une fois par CV depose par le recruteur).

import logging
from typing import TypedDict, Optional

from langgraph.graph import StateGraph, END

from agents.agent1_extraction import extraire_cv, extraire_offre
from agents.agent2_matching import calculer_matching
from agents.agent3_generation import generer_questions_entretien
from agents.agent4_evaluation import evaluer_reponse_candidat
from db.db import (
    sauver_offre, sauver_candidat, sauver_matching,
    creer_entretien, sauver_questions,
    lister_questions_entretien, sauver_reponse, marquer_entretien_repondu,
)
from db.parametres_offre import obtenir_parametres_offre, mettre_a_jour_parametres_offre

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Etat partage du graphe
# ---------------------------------------------------------------------------

class PipelineState(TypedDict):
    # Entrees
    session_id: int
    texte_offre: str            # vide si l'offre a deja ete traitee pour cette session
    nom_fichier_cv: str
    texte_cv: str
    # NOUVEAU : preferences choisies par le recruteur AVANT le lancement
    # de l'analyse (ecran_nouvelle_session), a appliquer des le tout
    # premier calcul de matching. None = comportement par defaut.
    parametres_initiaux: Optional[dict]

    # Sorties intermediaires, remplies au fur et a mesure par les noeuds
    offre_id: Optional[int]
    offre_json: Optional[dict]
    candidat_id: Optional[int]
    profil_json: Optional[dict]
    resultat_matching: Optional[dict]


# ---------------------------------------------------------------------------
# 2. Noeuds du graphe (chacun appelle un agent existant, inchange)
# ---------------------------------------------------------------------------

def noeud_extraction_offre(state: PipelineState) -> PipelineState:
    """Extrait l'offre (Agent 1) et la sauvegarde. A ne faire qu'une fois
    par session : si offre_id est deja fourni, ce noeud est saute
    (voir construire_pipeline)."""

    logger.info("Extraction de l'offre...")
    offre_json = extraire_offre(state["texte_offre"])
    offre_id = sauver_offre(state["session_id"], state["texte_offre"], offre_json)

    # NOUVEAU : si le recruteur a choisi des preferences de matching des
    # l'ecran de depot (plafond anti-inflation, etc.), on les enregistre
    # tout de suite, AVANT le noeud_matching qui suit dans le meme
    # pipeline.invoke() -- sinon le premier candidat serait quand meme
    # calcule avec les valeurs par defaut.
    if state.get("parametres_initiaux"):
        mettre_a_jour_parametres_offre(offre_id, state["parametres_initiaux"])

    state["offre_id"] = offre_id
    state["offre_json"] = offre_json
    return state


def noeud_extraction_cv(state: PipelineState) -> PipelineState:
    """Extrait le CV du candidat (Agent 1) et le sauvegarde."""

    logger.info("Extraction du CV : %s", state["nom_fichier_cv"])
    profil_json = extraire_cv(state["texte_cv"])
    candidat_id = sauver_candidat(
        state["session_id"],
        state["nom_fichier_cv"],
        state["texte_cv"],
        profil_json,
    )

    state["candidat_id"] = candidat_id
    state["profil_json"] = profil_json
    return state


def noeud_matching(state: PipelineState) -> PipelineState:
    """Calcule le score de compatibilite (Agent 2) et le sauvegarde."""

    logger.info("Calcul du matching pour candidat_id=%s", state["candidat_id"])
    # NOUVEAU : recuperer les preferences du recruteur pour cette offre
    # (plafond anti-inflation, etc.) et les transmettre a l'Agent 2.
    # Sans offre_id (ne devrait pas arriver), on retombe sur le
    # comportement par defaut (parametres vides -> valeurs d'origine).
    parametres = obtenir_parametres_offre(state["offre_id"]) if state.get("offre_id") else {}
    resultat = calculer_matching(state["profil_json"], state["offre_json"], parametres)

    sauver_matching(
        state["candidat_id"],
        resultat["score_compatibilite"],
        resultat["niveau_correspondance"],
        resultat,
    )

    state["resultat_matching"] = resultat
    return state


# ---------------------------------------------------------------------------
# 3. Construction du graphe
# ---------------------------------------------------------------------------

def construire_pipeline(avec_extraction_offre: bool = True):
    """
    avec_extraction_offre=True  : offre + CV extraits dans le meme appel
        (premier CV d'une session -> offre pas encore en base).
    avec_extraction_offre=False : offre deja extraite (fournie via
        offre_json dans l'etat initial) -> on ne refait pas l'appel LLM
        pour chaque CV suivant de la meme session.
    """

    graph = StateGraph(PipelineState)

    if avec_extraction_offre:
        graph.add_node("extraction_offre", noeud_extraction_offre)
        graph.add_node("extraction_cv", noeud_extraction_cv)
        graph.add_node("matching", noeud_matching)

        graph.set_entry_point("extraction_offre")
        graph.add_edge("extraction_offre", "extraction_cv")
        graph.add_edge("extraction_cv", "matching")
        graph.add_edge("matching", END)
    else:
        graph.add_node("extraction_cv", noeud_extraction_cv)
        graph.add_node("matching", noeud_matching)

        graph.set_entry_point("extraction_cv")
        graph.add_edge("extraction_cv", "matching")
        graph.add_edge("matching", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# 4. Fonctions d'appel simples (a utiliser depuis app.py)
# ---------------------------------------------------------------------------

def traiter_premier_cv(session_id: int, texte_offre: str,
                        nom_fichier_cv: str, texte_cv: str,
                        parametres_initiaux: dict = None) -> PipelineState:
    """A appeler pour le PREMIER CV d'une session : extrait aussi l'offre.

    parametres_initiaux : preferences de matching choisies par le
    recruteur des l'ecran de depot (ex. plafond anti-inflation), a
    appliquer avant meme le calcul du premier candidat."""

    pipeline = construire_pipeline(avec_extraction_offre=True)
    etat_initial: PipelineState = {
        "session_id": session_id,
        "texte_offre": texte_offre,
        "nom_fichier_cv": nom_fichier_cv,
        "texte_cv": texte_cv,
        "parametres_initiaux": parametres_initiaux,
        "offre_id": None,
        "offre_json": None,
        "candidat_id": None,
        "profil_json": None,
        "resultat_matching": None,
    }
    return pipeline.invoke(etat_initial)


# ---------------------------------------------------------------------------
# 5. Agent 3 et Agent 4 : appeles hors du StateGraph (declenches par une
#    action recruteur/candidat, pas par un enchainement automatique).
# ---------------------------------------------------------------------------

def lancer_entretien(
    candidat: dict,
    offre_json: dict,
    email_candidat: str,
    nb_questions: int,
    niveau_difficulte: str,
) -> str:
    """
    Genere les questions (Agent 3), les sauvegarde, cree un entretien avec
    token unique et envoie le lien par email au candidat.

    Args:
        candidat: dict issu de db.get_candidat / lister_candidats_session
            (doit contenir "id", "json_extrait", "json_matching").
        offre_json: offre structuree de la session.
        email_candidat: adresse email a laquelle envoyer le lien.
        nb_questions: nombre de questions choisi par le recruteur pour
            CET entretien (3 a 8). Etape 3 : obligatoire, choisi
            explicitement dans l'UI, pas de valeur par defaut ici.
        niveau_difficulte: "facile" | "moyen" | "difficile", choisi par
            le recruteur pour CET entretien. Etape 3 : obligatoire.

    Returns:
        Le token genere (utile pour affichage/tests).
    """
    import uuid
    from email_utils.envoi import envoyer_lien_entretien

    logger.info(
        "Generation des questions pour candidat_id=%s (nb_questions=%s, difficulte=%s)",
        candidat["id"], nb_questions, niveau_difficulte,
    )
    resultat = generer_questions_entretien(
        profil=candidat["json_extrait"],
        offre=offre_json,
        resultat_agent2=candidat.get("json_matching"),
        nb_questions=nb_questions,
        niveau_difficulte=niveau_difficulte,
    )

    token = uuid.uuid4().hex
    entretien_id = creer_entretien(
        candidat["id"], token,
        nb_questions_utilise=nb_questions,
        niveau_difficulte_utilise=niveau_difficulte,
    )
    sauver_questions(entretien_id, resultat["questions"])

    nom_candidat = (candidat["json_extrait"] or {}).get("nom", "")
    envoyer_lien_entretien(email_candidat, nom_candidat, token)

    return token


def traiter_reponses_candidat(entretien_id: int, reponses: dict[int, str]):
    """
    Evalue chaque reponse du candidat (Agent 4) et sauvegarde le resultat.

    Args:
        entretien_id: id de l'entretien.
        reponses: dict {question_id: texte_reponse}.
    """
    questions = {q["id"]: q for q in lister_questions_entretien(entretien_id)}

    for question_id, texte_reponse in reponses.items():
        question = questions.get(question_id)
        if question is None:
            continue
        logger.info("Evaluation reponse question_id=%s", question_id)
        evaluation = evaluer_reponse_candidat(question["texte"], texte_reponse)
        sauver_reponse(question_id, texte_reponse, evaluation)

    marquer_entretien_repondu(entretien_id)


def traiter_cv_suivant(session_id: int, offre_json: dict,
                        nom_fichier_cv: str, texte_cv: str,
                        offre_id: int = None) -> PipelineState:
    """A appeler pour les CV suivants de la MEME session : reutilise
    l'offre deja extraite, evite un appel LLM inutile.

    offre_id doit etre transmis (recupere depuis l'etat retourne par
    traiter_premier_cv) pour que noeud_matching puisse lire les
    parametres de matching propres a cette offre (plafond anti-inflation,
    etc.). Sans lui, ces preferences seraient silencieusement ignorees."""

    pipeline = construire_pipeline(avec_extraction_offre=False)
    etat_initial: PipelineState = {
        "session_id": session_id,
        "texte_offre": "",
        "nom_fichier_cv": nom_fichier_cv,
        "texte_cv": texte_cv,
        "parametres_initiaux": None,
        "offre_id": offre_id,
        "offre_json": offre_json,
        "candidat_id": None,
        "profil_json": None,
        "resultat_matching": None,
    }
    return pipeline.invoke(etat_initial)