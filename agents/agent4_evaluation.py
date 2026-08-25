# agents/agent4_evaluation.py

import logging

from utils.llm_client import appeler_gemini_json

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Structured output (schema JSON)
# ---------------------------------------------------------------------------

SCHEMA_EVALUATION_REPONSE = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "minimum": 0, "maximum": 100},
        "niveau_reponse": {
            "type": "string",
            "enum": ["Insuffisant", "Moyen", "Bon", "Très bon", "Excellent"],
        },
        "points_forts": {
            "type": "array",
            "items": {"type": "string"}
        },
        "axes_amelioration": {
            "type": "array",
            "items": {"type": "string"}
        },
        "feedback": {"type": "string"},
    },
    "required": [
        "score",
        "niveau_reponse",
        "points_forts",
        "axes_amelioration",
        "feedback",
    ],
}


# ---------------------------------------------------------------------------
# 2. Prompt
# ---------------------------------------------------------------------------

PROMPT_AGENT4 = """Tu es un système d'évaluation des réponses de candidats en entretien, pour
un outil de recrutement spécialisé IT/IA. Tu reçois une question d'entretien
et la réponse donnée par le candidat.

Ta mission : évaluer la qualité de la réponse et produire un feedback
constructif.

Règles strictes :
- Base-toi uniquement sur le contenu réel de la réponse du candidat.
  N'invente aucune compétence ou expérience qu'il n'a pas mentionnée.
- Le score doit être un nombre entier entre 0 et 100, reflétant la
  pertinence, la précision et la complétude de la réponse par rapport à ce
  qui était demandé.
- Le niveau_reponse doit être choisi UNIQUEMENT parmi ces catégories, selon
  ce mapping strict avec le score :
    "Insuffisant" : score de 0 à 39
    "Moyen"       : score de 40 à 59
    "Bon"         : score de 60 à 74
    "Très bon"    : score de 75 à 89
    "Excellent"   : score de 90 à 100
- Liste les points forts réels de la réponse (ce que le candidat a bien
  couvert).
- Liste les axes d'amélioration (ce qui manque, ce qui aurait pu être
  approfondi ou précisé).
- Le feedback doit rester factuel et constructif, SANS aucun jugement sur
  la personnalité, l'intelligence ou la valeur du candidat — évalue
  uniquement le contenu de la réponse.
- Reste un outil d'assistance au recruteur : ne formule aucune décision
  finale d'embauche.
"""


# ---------------------------------------------------------------------------
# 3. Dérivation déterministe du niveau (filet de sécurité)
#
# Même principe que deriver_niveau() dans agent2_matching.py : le LLM
# reçoit déjà le mapping dans le prompt + un enum contraint dans le
# schéma, mais on recalcule quand même le niveau nous-mêmes à partir
# du score renvoyé, pour une garantie à 100% (aucune dépendance à ce
# que le LLM applique correctement le mapping).
# ---------------------------------------------------------------------------

def deriver_niveau_reponse(score: int) -> str:
    if score < 40:
        return "Insuffisant"
    elif score < 60:
        return "Moyen"
    elif score < 75:
        return "Bon"
    elif score < 90:
        return "Très bon"
    else:
        return "Excellent"


# ---------------------------------------------------------------------------
# 4. Fonction principale de l'Agent 4
# ---------------------------------------------------------------------------

def evaluer_reponse_candidat(question: str, reponse_candidat: str) -> dict:
    """
    Point d'entrée de l'Agent 4.

    Args:
        question: la question d'entretien posée (sortie de l'Agent 3,
            champ "question").
        reponse_candidat: la réponse libre donnée par le candidat
            (texte brut, saisi par le recruteur ou transcrit).

    Returns:
        dict conforme à SCHEMA_EVALUATION_REPONSE :
        {"score", "niveau_reponse", "points_forts",
         "axes_amelioration", "feedback"}
        Le "niveau_reponse" est recalculé de façon déterministe à
        partir du "score" avant d'être retourné (cf. deriver_niveau_reponse).
    """

    prompt = (
        PROMPT_AGENT4
        + "\n\nQuestion posée au candidat :\n"
        + question
        + "\n\nRéponse du candidat :\n"
        + reponse_candidat
    )

    resultat = appeler_gemini_json(
        prompt,
        model="gemini-3.5-flash-lite",
        thinking_level="medium",
        response_schema=SCHEMA_EVALUATION_REPONSE,
    )

    # Filet de sécurité déterministe : le score prime, le niveau en
    # découle toujours, quoi qu'ait répondu le LLM sur ce champ.
    resultat["niveau_reponse"] = deriver_niveau_reponse(resultat["score"])

    return resultat