# agents/agent1_extraction.py
from utils.llm_client import appeler_gemini_json

SCHEMA_AGENT1 = {
    "type": "object",
    "properties": {
        "nom": {"type": "string"},
        "titre_professionnel": {"type": "string", "nullable": True},
        "resume": {"type": "string", "nullable": True},
        "contact": {
            "type": "object",
            "properties": {
                "email": {"type": "string", "nullable": True},
                "telephone": {"type": "string", "nullable": True},
                "ville": {"type": "string", "nullable": True},
                "linkedin": {"type": "string", "nullable": True}
            }
        },
        "competences_techniques": {
            "type": "array",
            "items": {"type": "string"}
        },
        "competences_transversales": {
            "type": "array",
            "items": {"type": "string"}
        },
        "langues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "langue": {"type": "string"},
                    "niveau": {"type": "string", "nullable": True}
                },
                "required": ["langue"]
            }
        },
        "experiences": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "poste": {"type": "string"},
                    "entreprise": {"type": "string", "nullable": True},
                    "date_debut": {"type": "string", "nullable": True},
                    "date_fin": {"type": "string", "nullable": True},
                    "ville": {"type": "string", "nullable": True},
                    "description": {"type": "string", "nullable": True}
                },
                "required": ["poste"]
            }
        },
        "formations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "intitule": {"type": "string"},
                    "etablissement": {"type": "string", "nullable": True},
                    "annee_debut": {"type": "string", "nullable": True},
                    "annee_fin": {"type": "string", "nullable": True}
                },
                "required": ["intitule"]
            }
        },
        "certifications": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "nom": {"type": "string"},
                    "organisme": {"type": "string", "nullable": True},
                    "annee": {"type": "string", "nullable": True}
                },
                "required": ["nom"]
            }
        },
        "centres_interet": {
            "type": "array",
            "items": {"type": "string"}
        }
    },
    "required": ["nom", "competences_techniques", "experiences", "formations"]
}

PROMPT_AGENT1 = """Tu es un système d'extraction d'informations de CV pour un outil de recrutement.

Voici un CV. Extrais uniquement les informations réellement présentes dans le document, selon le schéma structuré défini.

Règles strictes :
- N'invente aucune information absente du CV. Si une information n'existe pas, laisse le champ vide ou null.
- Distingue bien les compétences techniques (langages, outils, technologies) des compétences transversales/qualités (soft skills comme leadership, communication, rigueur).
- Pour chaque expérience, extrais les dates telles qu'elles apparaissent littéralement dans le CV, sans les reformuler (exemple : si le CV écrit "2017 : aujourd'hui", garde exactement "2017" et "aujourd'hui" dans date_debut et date_fin, ne les convertis pas en autre format).
- Ne calcule aucune durée ou total : ton rôle est uniquement d'extraire, pas de calculer.
- Pour competences_techniques : chaque item doit être ATOMIQUE (un seul concept par entrée : un langage, un outil, une techno). N'associe JAMAIS un terme générique d'action (ex : "programmation", "maîtrise de", "utilisation de", "connaissance de") avec le nom de la techno dans la même chaîne.
  Exemple INCORRECT : "programmation Python", "programmation R"
  Exemple CORRECT : "Python", "R"
- N'utilise jamais deux formulations différentes pour désigner la même compétence dans la même sortie (pas de doublon sémantique).
"""


# ---------------------------------------------------------------------------
# Normalisation déterministe des compétences (post-traitement, sans LLM)
#
# But : même si le LLM ne suit pas parfaitement la règle d'atomicité du
# prompt (variance résiduelle inévitable avec un LLM), cette fonction
# garantit un résultat STABLE et REPRODUCTIBLE à partir d'une même sortie
# brute, en supprimant les préfixes génériques d'action qui créent des
# doublons de granularité (ex: "programmation Python" vs "Python").
# ---------------------------------------------------------------------------

PREFIXES_GENERIQUES = [
    "programmation",
    "maîtrise de",
    "maitrise de",
    "maîtrise du",
    "maitrise du",
    "utilisation de",
    "utilisation du",
    "connaissance de",
    "connaissance du",
    "expérience en",
    "experience en",
    "expérience avec",
    "experience avec",
]


def _normaliser_item(item: str) -> str:
    """Retire un préfixe générique d'action d'un item de compétence, s'il y en a un."""
    item_strip = item.strip()
    item_lower = item_strip.lower()
    for prefixe in PREFIXES_GENERIQUES:
        if item_lower.startswith(prefixe + " "):
            reste = item_strip[len(prefixe):].strip()
            if reste:  # ne garder le "reste" que s'il n'est pas vide
                return reste
    return item_strip


def normaliser_competences(competences: list[str]) -> list[str]:
    """
    Normalise une liste de compétences pour la rendre stable/reproductible :
    1. Supprime les préfixes génériques d'action ("programmation X" -> "X").
    2. Déduplique de façon insensible à la casse, en gardant la première
       formulation rencontrée, tout en préservant l'ordre d'apparition.

    Cette fonction est déterministe (aucun appel LLM) : appliquée à une
    même liste d'entrée, elle produit toujours la même liste de sortie.
    """
    normalisees = [_normaliser_item(c) for c in competences if c and c.strip()]

    vues = set()
    resultat = []
    for item in normalisees:
        cle = item.lower()
        if cle not in vues:
            vues.add(cle)
            resultat.append(item)
    return resultat


def extraire_cv(texte_cv: str) -> dict:
    """
    Extrait les informations structurées d'un CV brut (texte).

    Args:
        texte_cv: le contenu textuel du CV (déjà extrait du PDF en amont).

    Returns:
        dict: les informations structurées du CV selon SCHEMA_AGENT1.
    """
    resultat = appeler_gemini_json(
        prompt=PROMPT_AGENT1 + "\n\nCV :\n" + texte_cv,
        model="gemini-3.5-flash-lite",
        thinking_level="low",
        response_schema=SCHEMA_AGENT1,
    )

    # Normalisation déterministe : élimine la variance de granularité
    # (ex: "programmation Python" vs "Python") avant transmission à Agent 2.
    # NB : on utilise `.get(...) or []` et pas `.get(..., [])` car le champ
    # peut être présent dans le JSON avec la valeur explicite `null` (pas
    # seulement absent) — `.get(clé, [])` ne protège pas contre ce cas et
    # ferait planter normaliser_competences() en itérant sur None.
    resultat["competences_techniques"] = normaliser_competences(
        resultat.get("competences_techniques") or []
    )
    resultat["competences_transversales"] = normaliser_competences(
        resultat.get("competences_transversales") or []
    )

    return resultat


# ---------------------------------------------------------------------------
# Extraction de l'offre d'emploi
# (nécessaire pour que l'Agent 2 puisse comparer profil candidat / offre)
# ---------------------------------------------------------------------------

SCHEMA_OFFRE = {
    "type": "object",
    "properties": {
        "intitule_poste": {"type": "string"},
        "entreprise": {"type": "string", "nullable": True},
        "ville": {"type": "string", "nullable": True},
        "type_contrat": {"type": "string", "nullable": True},
        "experience_requise": {"type": "string", "nullable": True},
        "competences_techniques_requises": {
            "type": "array",
            "items": {"type": "string"}
        },
        "competences_transversales_requises": {
            "type": "array",
            "items": {"type": "string"}
        },
        "niveau_etudes_requis": {"type": "string", "nullable": True},
        "langues_requises": {
            "type": "array",
            "items": {"type": "string"}
        },
        "description_poste": {"type": "string", "nullable": True}
    },
    "required": ["intitule_poste", "competences_techniques_requises"]
}

PROMPT_OFFRE = """Tu es un système d'extraction d'informations d'offres d'emploi pour un outil de recrutement.

Voici une offre d'emploi. Extrais uniquement les informations réellement présentes dans le document, selon le schéma structuré défini.

Règles strictes :
- N'invente aucune exigence absente de l'offre. Si une information n'existe pas, laisse le champ vide ou null.
- Distingue bien les compétences techniques (langages, outils, technologies) des compétences transversales/qualités (soft skills comme leadership, communication, rigueur).
- Extrais l'expérience requise telle qu'elle apparaît littéralement dans l'offre (exemple : "5 ans minimum"), sans la reformuler ni la convertir.
- Ne déduis et n'ajoute aucune exigence qui ne serait pas explicitement mentionnée dans le texte.
- Pour competences_techniques_requises : chaque item doit être ATOMIQUE (un seul concept par entrée : un langage, un outil, une techno, une méthode nommée). N'associe JAMAIS un terme générique d'action (ex : "programmation", "maîtrise de", "connaissance de") avec le nom de la techno dans la même chaîne.
  Exemple INCORRECT : "programmation Python", "programmation R", "programmation Genstat"
  Exemple CORRECT : "Python", "R", "Genstat"
  Si le texte mentionne un terme générique sans techno associée (ex : "capacités de programmation" en général), il peut figurer une seule fois comme item séparé, mais ne doit jamais être dupliqué en préfixe d'autres items.
- N'utilise jamais deux formulations différentes pour désigner la même exigence dans la même sortie (pas de doublon sémantique).
"""


def extraire_offre(texte_offre: str) -> dict:
    """
    Extrait les informations structurées d'une offre d'emploi brute (texte).

    Args:
        texte_offre: le contenu textuel de l'offre (déjà extrait du PDF en amont).

    Returns:
        dict: les informations structurées de l'offre selon SCHEMA_OFFRE.
    """
    resultat = appeler_gemini_json(
        prompt=PROMPT_OFFRE + "\n\nOffre d'emploi :\n" + texte_offre,
        model="gemini-3.5-flash-lite",
        thinking_level="low",
        response_schema=SCHEMA_OFFRE,
    )

    # Normalisation déterministe : c'est précisément ici (compétences
    # techniques requises par l'offre) que la variance a été observée
    # dans les tests ("programmation Python" vs "Python" + "programmation").
    resultat["competences_techniques_requises"] = normaliser_competences(
        resultat.get("competences_techniques_requises") or []
    )
    resultat["competences_transversales_requises"] = normaliser_competences(
        resultat.get("competences_transversales_requises") or []
    )

    return resultat