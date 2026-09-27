# agents/agent3_generation.py

import json
import logging

import faiss
from sentence_transformers import SentenceTransformer

from utils.llm_client import appeler_gemini_json


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Chargement paresseux (lazy singleton) de l'index FAISS + du modele
# d'embeddings, sur le meme principe que obtenir_modele_embeddings()
# dans agent2_matching.py.
# ---------------------------------------------------------------------------

INDEX_PATH = "data/questions_bank/corpus_index.faiss"
METADATA_PATH = "data/questions_bank/corpus_metadata.json"

_index_faiss = None
_metadata_corpus = None
_modele_embeddings = None


def _charger_ressources():
    """Charge l'index FAISS, les metadonnees et le modele d'embeddings
    une seule fois (reutilises a chaque appel de l'agent)."""

    global _index_faiss, _metadata_corpus, _modele_embeddings

    if _index_faiss is None:
        logger.info("Chargement de l'index FAISS (%s)...", INDEX_PATH)
        _index_faiss = faiss.read_index(INDEX_PATH)

    if _metadata_corpus is None:
        with open(METADATA_PATH, "r", encoding="utf-8") as f:
            _metadata_corpus = json.load(f)

    if _modele_embeddings is None:
        logger.info("Chargement du modele d'embeddings (premiere utilisation)...")
        _modele_embeddings = SentenceTransformer(
            "paraphrase-multilingual-MiniLM-L12-v2"
        )

    return _index_faiss, _metadata_corpus, _modele_embeddings


# ---------------------------------------------------------------------------
# 1. Construction des requetes de retrieval
# ---------------------------------------------------------------------------
#
# Choix de conception (voir discussion) : on n'envoie PAS une seule
# requete "fourre-tout" (profil + offre + ecarts concatenes), car un
# vecteur moyen dilue le signal de chaque element individuel.
#
# A la place : une requete FAISS SEPAREE par point_manquant, par
# competence cle de l'offre, et (optionnel) par point_fort. Chaque
# requete ramene son propre top-k, qu'on fusionne et dedoublonne
# ensuite. Ca garantit structurellement que chaque ecart individuel du
# candidat a une chance d'etre couvert par le pool de questions
# transmis a Gemini, plutot que de dependre uniquement de la consigne
# du prompt.
# ---------------------------------------------------------------------------

NB_COMPETENCES_OFFRE_RETENUES = 5
NB_POINTS_FORTS_RETENUS = 2

# nb_questions dynamique : avec un nombre fixe (5), Gemini est force a
# choisir entre les ecarts et sacrifie systematiquement certains
# points_manquants (observe en test sur cv4 : "gestion de projet"
# jamais couvert malgre le retrieval dedie). On adapte donc le nombre
# de questions au nombre d'ecarts reels du candidat.
NB_QUESTIONS_BASE = 4
NB_QUESTIONS_MAX = 8

# NOUVEAU (etape 3) : consigne de difficulte injectee dans le prompt.
# "moyen" reproduit exactement la formulation implicite du prompt
# d'origine (aucune consigne de difficulte explicite) : c'est le
# niveau par defaut, sans changement de comportement pour ce niveau.
NIVEAUX_DIFFICULTE = {
    "facile": (
        "Niveau de difficulte demande : FACILE. Pose des questions "
        "d'introduction/decouverte, formulees simplement, qui permettent "
        "au candidat de reformuler ce qu'il connait deja sans piege ni "
        "cas limite. Evite les questions a plusieurs niveaux de "
        "profondeur ou les mises en situation complexes."
    ),
    "moyen": (
        "Niveau de difficulte demande : MOYEN. Pose des questions "
        "standard d'entretien technique, qui demandent une explication "
        "ou une justification claire, sans etre des cas limites ou des "
        "pieges."
    ),
    "difficile": (
        "Niveau de difficulte demande : DIFFICILE. Pose des questions "
        "exigeantes qui demandent une analyse approfondie, une mise en "
        "situation concrete avec contraintes, ou la comparaison de "
        "plusieurs approches/compromis. Vise a distinguer un candidat "
        "confirme d'un candidat qui ne maitrise le sujet qu'en surface."
    ),
}


def calculer_nb_questions(resultat_agent2: dict | None) -> int:
    """nb_questions = base + 1 par point_manquant, plafonne a
    NB_QUESTIONS_MAX pour ne pas surcharger l'entretien reel."""

    resultat_agent2 = resultat_agent2 or {}
    nb_ecarts = len(resultat_agent2.get("points_manquants") or [])
    return min(NB_QUESTIONS_MAX, NB_QUESTIONS_BASE + nb_ecarts)


def construire_requetes_retrieval(
    profil: dict,
    offre: dict,
    resultat_agent2: dict | None,
) -> list[tuple[str, str]]:
    """
    Construit la liste des requetes FAISS a executer, sous forme de
    tuples (label, texte_requete). Le label sert uniquement au
    logging/diagnostic, pas a la recherche elle-meme.

    Sources utilisees, par ordre de priorite :
    1. points_manquants (Agent 2)      -> une requete par ecart
    2. competences cles de l'offre      -> une requete groupee
    3. points_forts (Agent 2)           -> une requete groupee (optionnel)

    Si resultat_agent2 est None (l'Agent 3 doit pouvoir tourner sans
    l'Agent 2, cf. discussion), seule la requete (2) est construite.
    """

    requetes = []

    resultat_agent2 = resultat_agent2 or {}
    points_manquants = resultat_agent2.get("points_manquants") or []
    points_forts = resultat_agent2.get("points_forts") or []

    # 1. Une requete DEDIEE par point_manquant : c'est le filet de
    # securite structurel qui garantit que le principal ecart du
    # candidat a des questions pertinentes disponibles, sans dependre
    # uniquement du prompt.
    for point in points_manquants:
        requetes.append((f"ecart: {point}", point))

    # 2. Une requete groupee sur les competences cles de l'offre
    # (coeur du poste), limitee aux premieres pour ne pas diluer le
    # signal avec une trop longue liste.
    competences_offre = (
        (offre.get("competences_techniques_requises") or [])
        + (offre.get("competences_transversales_requises") or [])
    )[:NB_COMPETENCES_OFFRE_RETENUES]

    if competences_offre:
        requetes.append((
            "competences_offre",
            " ; ".join(competences_offre),
        ))

    # 3. Une requete groupee sur quelques points_forts, pour permettre
    # une question d'approfondissement sur ce que le candidat dit
    # maitriser (verifier que ce n'est pas un mot-cle isole).
    if points_forts:
        requetes.append((
            "points_forts",
            " ; ".join(points_forts[:NB_POINTS_FORTS_RETENUS]),
        ))

    return requetes


# ---------------------------------------------------------------------------
# 2. Retrieval FAISS (une requete -> top-k questions)
# ---------------------------------------------------------------------------

K_PAR_REQUETE = 6


def rechercher_questions_similaires(requete: str, k: int = K_PAR_REQUETE) -> list:
    """
    Recherche les k questions du corpus les plus proches semantiquement
    d'UNE requete, via similarite cosinus dans l'index FAISS.

    Retourne une liste de dicts (memes champs que le corpus :
    id, texte, type, domaine), enrichis d'un champ "similarite".
    """

    index, metadata, modele = _charger_ressources()

    vecteur_requete = modele.encode([requete], convert_to_numpy=True)
    faiss.normalize_L2(vecteur_requete)

    k = min(k, index.ntotal)
    similarites, indices = index.search(vecteur_requete, k)

    resultats = []
    for rang, idx in enumerate(indices[0]):
        if idx < 0:
            continue
        question = dict(metadata[idx])
        question["similarite"] = float(similarites[0][rang])
        resultats.append(question)

    return resultats


def construire_pool_questions(
    profil: dict,
    offre: dict,
    resultat_agent2: dict | None,
) -> list:
    """
    Execute toutes les requetes de retrieval (une par point_manquant,
    plus les requetes groupees offre/points_forts), fusionne les
    resultats et dedoublonne par id.

    Retourne le pool final de questions candidates, transmis ensuite
    a Gemini comme source d'inspiration.
    """

    requetes = construire_requetes_retrieval(profil, offre, resultat_agent2)

    pool = {}  # id -> question (dedoublonnage)

    for label, texte_requete in requetes:
        resultats = rechercher_questions_similaires(texte_requete)

        logger.debug(
            "Requete '%s' (%s) -> %d resultats",
            label,
            texte_requete[:60],
            len(resultats),
        )

        for question in resultats:
            # En cas de doublon (meme question retrouvee par plusieurs
            # requetes), on garde la similarite la plus elevee.
            existant = pool.get(question["id"])
            if existant is None or question["similarite"] > existant["similarite"]:
                pool[question["id"]] = question

    return list(pool.values())


# ---------------------------------------------------------------------------
# 3. Prompt et schema de generation (rapport, section 4.3 / 4.4)
# ---------------------------------------------------------------------------

SCHEMA_QUESTIONS_ENTRETIEN = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "type": {
                        "type": "string",
                        "enum": ["technique", "comportementale", "situationnelle"],
                    },
                    "competence_ciblee": {"type": "string"},
                    "justification": {"type": "string"},
                },
                "required": [
                    "question",
                    "type",
                    "competence_ciblee",
                    "justification",
                ],
            },
        }
    },
    "required": ["questions"],
}


def construire_prompt(
    profil: dict,
    offre: dict,
    pool_questions: list,
    points_manquants: list | None = None,
    nb_questions: int = 5,
    niveau_difficulte: str = "moyen",
) -> str:
    """Construit le prompt final envoye a Gemini, base sur le prompt du
    rapport (section 4.3), complete par deux regles ajoutees suite au
    test comparatif RAG/sans RAG :
    1. liste EXPLICITE des points_manquants a couvrir un par un
       (auparavant seulement une consigne generique "priorise le
       principal point d'ecart", qui laissait Gemini en sacrifier
       certains quand ils etaient plusieurs) ;
    2. contrainte "un seul concept par question" (les questions
       observees en test empilaient parfois plusieurs notions
       techniques distinctes en une seule phrase, les rendant confuses
       pour un entretien reel).
    """

    questions_formattees = "\n".join(
        f"- ({q['domaine']}, {q['type']}) {q['texte']}"
        for q in pool_questions
    ) or "(aucune question similaire disponible)"

    consigne_difficulte = NIVEAUX_DIFFICULTE.get(
        niveau_difficulte, NIVEAUX_DIFFICULTE["moyen"]
    )

    points_manquants = points_manquants or []
    if points_manquants:
        points_manquants_formattes = "\n".join(f"- {p}" for p in points_manquants)
        consigne_ecarts = f"""Liste des points d'ecart entre le profil et l'offre (sortie de
l'Agent 2, matching CV/offre) :
{points_manquants_formattes}

- Assure-toi qu'AU MOINS UNE question couvre CHACUN des points d'ecart
  listes ci-dessus, pas seulement le premier ou le plus evident. Ne les
  regroupe pas entre eux dans une seule question, et ne les remplace
  pas par des questions portant uniquement sur les points forts du
  candidat."""
    else:
        consigne_ecarts = (
            "Aucun ecart connu entre le profil et l'offre (candidat "
            "tres compatible) : concentre les questions sur les "
            "competences cles de l'offre pour approfondir le niveau "
            "reel du candidat."
        )

    return f"""Tu es un systeme de generation de questions d'entretien pour un outil de
recrutement specialise IT/IA. Tu recois : un profil candidat structure, une
offre d'emploi, la liste des ecarts identifies par l'Agent 2, et une liste
de questions similaires deja existantes (recuperees via recherche
vectorielle dans une base de questions).

Ta mission : generer {nb_questions} questions d'entretien personnalisees, adaptees au
profil precis du candidat et aux exigences de l'offre.

Regles strictes :
- Appuie-toi sur les questions similaires fournies comme source
  d'inspiration principale, mais adapte-les au profil reel du candidat
  (ne les recopie pas telles quelles).
- Chaque question doit cibler UN SEUL concept ou UNE SEULE competence
  principale. N'empile pas plusieurs notions techniques distinctes
  dans la meme question (par exemple, ne combine pas dans une seule
  question la gestion memoire, un choix d'architecture ET un outil de
  deploiement : choisis l'angle le plus pertinent et reste focalise
  dessus).
- Chaque question doit cibler un element concret du CV ou de l'offre (une
  competence, une experience, ou un ecart identifie entre le profil et
  l'offre).
- Varie les types de questions : technique, comportementale,
  situationnelle.
- N'invente aucune information sur le candidat qui ne soit pas dans son
  profil.
- Reste factuel et neutre : les questions doivent permettre d'evaluer le
  candidat, pas de le juger a l'avance.

{consigne_ecarts}

{consigne_difficulte}

Profil candidat (JSON) :
{json.dumps(profil, ensure_ascii=False, indent=2)}

Offre d'emploi (JSON) :
{json.dumps(offre, ensure_ascii=False, indent=2)}

Questions similaires recuperees par recherche vectorielle (source d'inspiration) :
{questions_formattees}
"""


# ---------------------------------------------------------------------------
# 4. Fonction principale de l'Agent 3
# ---------------------------------------------------------------------------

def generer_questions_entretien(
    profil: dict,
    offre: dict,
    resultat_agent2: dict | None = None,
    nb_questions: int | None = None,
    niveau_difficulte: str = "moyen",
) -> dict:
    """
    Point d'entree de l'Agent 3.

    Args:
        profil: profil candidat structure (sortie de l'Agent 1).
        offre: offre d'emploi structuree.
        resultat_agent2: sortie complete de l'Agent 2 (dict contenant
            notamment "points_manquants" et "points_forts"). Optionnel :
            l'Agent 3 peut tourner sans l'Agent 2 (entretien
            exploratoire generique), auquel cas le retrieval se base
            uniquement sur les competences cles de l'offre.
        nb_questions: nombre de questions a generer par Gemini. Si
            None, calcule dynamiquement selon le nombre de
            points_manquants (cf. calculer_nb_questions). Depuis
            l'etape 3, ce choix est fait explicitement par le
            recruteur (via app.py) et n'est plus laisse a None dans
            le flux normal.
        niveau_difficulte: "facile" | "moyen" | "difficile" (etape 3).
            Choisi par le recruteur au moment de l'envoi. "moyen"
            reproduit exactement le comportement du prompt d'origine.

    Returns:
        dict conforme au schema SCHEMA_QUESTIONS_ENTRETIEN :
        {"questions": [{"question", "type", "competence_ciblee",
        "justification"}, ...]}
    """

    if nb_questions is None:
        nb_questions = calculer_nb_questions(resultat_agent2)

    points_manquants = (resultat_agent2 or {}).get("points_manquants") or []

    pool_questions = construire_pool_questions(profil, offre, resultat_agent2)

    logger.info(
        "Pool de %d questions candidates apres dedoublonnage (nb_questions=%d, difficulte=%s).",
        len(pool_questions),
        nb_questions,
        niveau_difficulte,
    )

    prompt = construire_prompt(
        profil,
        offre,
        pool_questions,
        points_manquants=points_manquants,
        nb_questions=nb_questions,
        niveau_difficulte=niveau_difficulte,
    )

    resultat = appeler_gemini_json(
        prompt,
        model="gemini-3.5-flash-lite",
        thinking_level="medium",
        response_schema=SCHEMA_QUESTIONS_ENTRETIEN,
    )

    return resultat


def generer_questions_entretien_sans_rag(
    profil: dict,
    offre: dict,
    resultat_agent2: dict | None = None,
    nb_questions: int | None = None,
    niveau_difficulte: str = "moyen",
) -> dict:
    """
    Version "sans RAG" de l'Agent 3, utilisee UNIQUEMENT pour le test
    comparatif (ablation study) mesurant l'apport reel du retrieval
    FAISS.

    Identique en tout point a generer_questions_entretien() (memes
    regles, meme schema, meme modele, meme temperature, meme
    thinking_level, meme nb_questions dynamique, meme liste explicite
    de points_manquants) SAUF que le pool de questions d'inspiration
    est vide : Gemini genere les questions uniquement a partir du
    profil et de l'offre, sans aucune question du corpus comme
    reference.

    C'est la SEULE variable qui change entre les deux versions (le
    pool RAG), pour que l'ecart observe en test soit imputable au
    retrieval et non a une difference de nb_questions ou de contenu
    du prompt.
    """

    if nb_questions is None:
        nb_questions = calculer_nb_questions(resultat_agent2)

    points_manquants = (resultat_agent2 or {}).get("points_manquants") or []

    prompt = construire_prompt(
        profil,
        offre,
        pool_questions=[],
        points_manquants=points_manquants,
        nb_questions=nb_questions,
        niveau_difficulte=niveau_difficulte,
    )

    resultat = appeler_gemini_json(
        prompt,
        model="gemini-3.5-flash-lite",
        thinking_level="medium",
        response_schema=SCHEMA_QUESTIONS_ENTRETIEN,
    )

    return resultat