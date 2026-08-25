# agents/agent2_matching.py

import json
import logging
import re
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher

import pysbd
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from text_to_num import alpha2digit

from utils.llm_client import appeler_gemini_json


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Segmenteur de phrases (remplace le split regex naïf sur "." / ";")
# ---------------------------------------------------------------------------
#
# L'ancien découpage `re.split(r"[.;]\s*", description)` coupait sur
# N'IMPORTE QUEL point, y compris dans les nombres décimaux ("15.3%"),
# les abréviations ("etc.") et les acronymes. pysbd fait une vraie
# segmentation de phrases (règles linguistiques FR), sans modèle à
# télécharger, ce qui règle ces cas sans regex maison à maintenir.
_segmenteur_phrases = pysbd.Segmenter(language="fr", clean=False)


def decouper_description(description: str) -> list:
    """Découpe une description en phrases via segmentation NLP
    (pysbd), au lieu d'un split naïf sur '.'/';'."""

    if not description:
        return []

    return [
        p.strip()
        for p in _segmenteur_phrases.segment(description)
        if p.strip()
    ]


# ---------------------------------------------------------------------------
# Modèle d'embeddings : chargement paresseux (lazy singleton)
# ---------------------------------------------------------------------------

_modele_embeddings = None


def obtenir_modele_embeddings() -> SentenceTransformer:
    global _modele_embeddings

    if _modele_embeddings is None:
        logger.info(
            "Chargement du modèle d'embeddings (première utilisation)..."
        )

        _modele_embeddings = SentenceTransformer(
            "paraphrase-multilingual-MiniLM-L12-v2"
        )

    return _modele_embeddings


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SEUIL_COUVERTURE_COMPETENCES = 0.58

# NOUVEAU : seuil plus strict quand le meilleur match trouvé est un
# simple mot-clé de compétence déclarée ("competence"), sans aucun
# contexte, plutôt qu'une phrase d'expérience/poste/formation
# ("narratif"). Un mot-clé isolé est une preuve plus faible : on exige
# une similarité plus élevée avant de le considérer comme suffisant.
# Corrige le cas "Gestion de projet" ~ "organisation" (sim 0.59,
# validé à tort sous l'ancien seuil unique de 0.58).
SEUIL_COUVERTURE_COMPETENCE_SEULE = 0.75

MODE_DIAGNOSTIC = True


# ---------------------------------------------------------------------------
# 0. Pondération des dimensions
# ---------------------------------------------------------------------------

POIDS_INITIAUX = {
    "competences": 0.35,
    "langues": 0.15,
    "niveau_etudes": 0.15,
    "experience": 0.25,
}


# ---------------------------------------------------------------------------
# Cap anti-inflation
# ---------------------------------------------------------------------------

SEUIL_CAP_ANTI_INFLATION = 0.35
SCORE_CAP_ANTI_INFLATION = 50


# ---------------------------------------------------------------------------
# 1. Segments candidat
# ---------------------------------------------------------------------------

def construire_segments_candidat(profil: dict) -> list:
    """
    Construit les segments utilisés pour le matching par embeddings.

    Sont pris en compte :
    - compétences techniques
    - compétences transversales
    - expériences (poste + description découpée phrase par phrase)
    - formations

    Les langues ne sont volontairement PAS incluses ici.

    NOUVEAU :
    Chaque segment est désormais taggé avec son "origine"
    ("competence" ou "narratif"), afin que le matching puisse
    appliquer un seuil de confiance différent selon le TYPE de
    preuve :

    - "competence" : un simple mot-clé auto-déclaré par le candidat
      (ex. "organisation"), sans aucun contexte ni preuve concrète.
    - "narratif" : une phrase tirée d'une expérience réelle, d'un
      intitulé de poste ou d'une formation — preuve contextualisée,
      plus fiable.

    Sans cette distinction, un mot-clé isolé et vague comme
    "organisation" peut sembler "prouver" une exigence précise comme
    "Gestion de projet" (similarité sémantique ~0.59), alors qu'un
    mot-clé seul, sans contexte, est une preuve beaucoup plus faible
    qu'une phrase d'expérience décrivant une action concrète.

    Retourne une liste de dicts : {"texte": str, "origine": str}
    """

    segments = []

    for competence in (
        (profil.get("competences_techniques") or [])
        +
        (profil.get("competences_transversales") or [])
    ):

        segments.append({
            "texte": competence,
            "origine": "competence"
        })

    for exp in profil.get("experiences") or []:

        # Le poste reste un segment à part entière
        # (utile pour matcher des exigences larges type "gestion de
        # projet") — traité comme "narratif" : un intitulé de poste
        # réel est une preuve plus concrète qu'un simple mot-clé.
        if exp.get("poste"):

            segments.append({
                "texte": exp["poste"],
                "origine": "narratif"
            })

        # La description est découpée phrase par phrase, au lieu
        # d'être concaténée en un seul long bloc de texte. Un long
        # paragraphe dilue l'embedding et fait rater des
        # correspondances pourtant explicites (ex. "Création de
        # pipelines Python" noyé dans 6 autres phrases). Résultat :
        # meilleur_match_cv pointera toujours vers une phrase
        # précise, plus juste ET plus lisible pour le recruteur.
        description = exp.get("description") or ""

        for phrase in decouper_description(description):

            segments.append({
                "texte": phrase,
                "origine": "narratif"
            })

    for form in profil.get("formations") or []:

        intitule = form.get("intitule", "")

        if intitule and intitule.strip():
            segments.append({
                "texte": intitule,
                "origine": "narratif"
            })

    # NOUVEAU : certifications. Auparavant totalement ignorées par le
    # matching (aucune référence à "certifications" dans tout le
    # fichier), alors qu'une certif (ex. "AWS Certified Solutions
    # Architect") est une preuve au moins aussi solide qu'une simple
    # ligne d'expérience — d'où le tag "narratif" (preuve
    # contextualisée/vérifiable), pas "competence" (mot-clé isolé).
    for cert in profil.get("certifications") or []:

        nom_cert = cert.get("nom", "")

        if nom_cert and nom_cert.strip():
            segments.append({
                "texte": nom_cert,
                "origine": "narratif"
            })

    return [
        s for s in segments
        if s["texte"] and s["texte"].strip()
    ]


# ---------------------------------------------------------------------------
# 1bis. Détection "outil précis" vs "exigence conceptuelle" (Option 3)
# ---------------------------------------------------------------------------
#
# PROBLÈME CORRIGÉ ICI :
# En matching purement sémantique (embeddings), un nom d'outil précis
# (Docker, Git, TensorFlow...) peut être faussement "couvert" parce
# qu'il est proche, dans l'espace vectoriel, d'un AUTRE outil du même
# domaine technique, sans aucun rapport réel :
#   "Docker" ~ "DAX"      (0.58)  -> candidat BI, aucun Docker
#   "Git"    ~ "ETL"      (0.63)  -> candidat BI, aucun Git
#   "Git"    ~ "Tableau"  (0.58)
#   "Docker" ~ "Jupyter"  (0.60)
# Ces quatre paires n'ont RIEN en commun fonctionnellement ; elles ne
# sont proches que parce que ce sont toutes des acronymes/outils du
# vocabulaire data. Chercher un nom d'outil précis dans des PHRASES
# LIBRES (expérience, description) est donc la mauvaise méthode.
#
# CORRECTIF (Option 3) :
# - "Outil précis" (pas de mot de liaison FR dans l'exigence, ex :
#   Docker, Git, TensorFlow, PyTorch, Python, SQL, scikit-learn) :
#   comparé UNIQUEMENT à la liste `competences_techniques` DÉCLARÉE
#   du candidat, via correspondance de chaîne floue (fuzzy match).
#   Le candidat doit l'avoir explicitement listé comme compétence.
# - "Exigence conceptuelle" (contient un mot de liaison, ex :
#   "traitement et analyse de données", "Gestion de projet",
#   "Résolution de problèmes") : reste sur le matching par embeddings
#   sur tous les segments candidat (expérience, formation, etc.),
#   car ces exigences ne sont normalement pas un simple mot du
#   vocabulaire technique et bénéficient de la compréhension
#   sémantique large.
# ---------------------------------------------------------------------------

_MOTS_LIAISON_FR = {
    "de", "des", "du", "d", "la", "le", "les", "l",
    "et", "en", "à", "a", "pour", "avec", "sur", "au", "aux",
    "un", "une", "dans", "par", "ou",
}

SEUIL_FUZZY_OUTIL = 0.75


def _est_outil_precis(item: str) -> bool:
    """
    Heuristique : une exigence est un "outil précis" (nom de
    techno/outil isolé, comparable à une entrée de liste de
    compétences) si elle ne contient AUCUN mot de liaison français
    typique d'une expression/phrase conceptuelle.

    "Docker", "Git", "TensorFlow", "scikit-learn", "Machine Learning"
        -> True (aucun mot de liaison)
    "traitement et analyse de données", "Gestion de projet"
        -> False (contient "et"/"de")

    Volontairement simple et sans liste figée d'outils à maintenir :
    la règle se base sur la STRUCTURE de l'expression, pas sur son
    contenu.
    """

    mots = re.findall(r"[a-zà-ÿ']+", item.lower())

    return not any(
        mot in _MOTS_LIAISON_FR
        for mot in mots
    )


def _normaliser_nom_outil(texte: str) -> str:
    """Normalisation stricte pour comparaison de noms d'outils :
    accents/casse retirés (via _normaliser_texte), puis espaces,
    tirets et points supprimés (ex: "scikit-learn" == "scikit learn"
    == "Scikit Learn")."""

    texte = _normaliser_texte(texte)

    return re.sub(r"[\s\-_.]", "", texte)


def _matcher_outil_precis(
    item: str,
    competences_techniques_candidat: list
):
    """
    Compare un nom d'outil précis exigé par l'offre à la liste des
    compétences techniques DÉCLARÉES par le candidat (jamais aux
    phrases libres de description/expérience), via correspondance
    de chaîne floue.

    Returns:
        (meilleur_match_ou_None, score_0_a_1)
    """

    if not competences_techniques_candidat:
        return None, 0.0

    item_norm = _normaliser_nom_outil(item)

    meilleur_match = None
    meilleur_score = 0.0

    for competence in competences_techniques_candidat:

        competence_norm = _normaliser_nom_outil(competence)

        if not competence_norm:
            continue

        if competence_norm == item_norm:
            score = 1.0
        else:
            score = SequenceMatcher(
                None,
                item_norm,
                competence_norm
            ).ratio()

        if score > meilleur_score:
            meilleur_score = score
            meilleur_match = competence

    return meilleur_match, meilleur_score


# ---------------------------------------------------------------------------
# 1ter. Couverture des compétences (dispatch outil précis / conceptuel)
# ---------------------------------------------------------------------------

def calculer_couverture_competences(
    items_requis: list,
    segments_candidat: list,
    competences_techniques_candidat: list = None,
    seuil: float = SEUIL_COUVERTURE_COMPETENCES,
    seuil_outil: float = SEUIL_FUZZY_OUTIL,
    items_techniques: list = None,
    seuil_competence_seule: float = SEUIL_COUVERTURE_COMPETENCE_SEULE
):
    """
    Pour chaque compétence requise, aiguille vers l'une des deux
    méthodes (voir section 1bis ci-dessus pour le détail) :

    - "Outil précis"        -> fuzzy match sur competences_techniques
                                DÉCLARÉES du candidat.
    - "Exigence conceptuelle" -> embeddings sur segments_candidat
                                (expérience, formation, compétences...).
                                Seuil variable selon l'origine du
                                meilleur segment trouvé (voir
                                seuil_competence_seule ci-dessous).

    IMPORTANT : la détection "outil précis" (_est_outil_precis) ne
    s'applique QU'AUX exigences techniques (items_techniques), jamais
    aux exigences transversales/soft skills. Sans cette restriction,
    un soft skill à un seul mot comme "Communication" ou "Autonomie"
    serait (à tort) traité comme un nom d'outil et cherché dans la
    liste des compétences techniques déclarées, où il ne se trouve
    jamais — d'où un faux "manquant" systématique. items_techniques
    doit donc contenir la liste des exigences *techniques* uniquement
    (sous-ensemble de items_requis) ; tout ce qui n'y figure pas est
    automatiquement traité comme conceptuel, quelle que soit sa
    structure grammaticale.

    NOUVEAU : segments_candidat est désormais une liste de dicts
    {"texte": str, "origine": "competence"|"narratif"} (voir
    construire_segments_candidat). Pour les exigences conceptuelles,
    si le meilleur segment trouvé est un simple mot-clé de compétence
    déclarée (origine="competence", sans contexte), le seuil de
    couverture appliqué est seuil_competence_seule (plus strict) au
    lieu de seuil. Un mot-clé isolé (ex. "organisation") est une
    preuve plus faible qu'une phrase d'expérience concrète (ex.
    "Création de pipelines Python"), il doit donc être nettement plus
    proche sémantiquement pour être accepté comme suffisant.

    Returns:
        (
            taux_couverture,
            items_couverts,
            items_manquants,
            details_matching   # dans le même ordre que items_requis
        )
    """

    competences_techniques_candidat = (
        competences_techniques_candidat or []
    )

    items_techniques = (
        set(items_techniques)
        if items_techniques is not None
        else set(items_requis)
    )

    # Aucun élément requis
    if not items_requis:

        return (
            1.0,
            [],
            [],
            []
        )

    items_outils = [
        item for item in items_requis
        if item in items_techniques
        and _est_outil_precis(item)
    ]

    items_conceptuels = [
        item for item in items_requis
        if item not in items_outils
    ]

    details_par_item = {}

    # -------------------------------------------------------
    # 1. Outils précis : fuzzy match sur compétences déclarées
    # -------------------------------------------------------

    for item in items_outils:

        meilleur_match, score = _matcher_outil_precis(
            item,
            competences_techniques_candidat
        )

        couvert = score >= seuil_outil

        details_par_item[item] = {
            "exigence_offre": item,
            "meilleur_match_cv": meilleur_match,
            "similarite": round(score, 4),
            "seuil": seuil_outil,
            "couvert": couvert,
            "methode": "outil_precis"
        }

        if MODE_DIAGNOSTIC:

            statut = "COUVERT" if couvert else "MANQUANT"

            logger.debug(
                '  [%s][outil_precis] "%s" -> '
                'similarité = %.3f '
                '(compétence déclarée la plus proche : "%s")',
                statut, item, score, meilleur_match
            )

    # -------------------------------------------------------
    # 2. Exigences conceptuelles : embeddings sur segments
    # -------------------------------------------------------

    if items_conceptuels:

        if not segments_candidat:

            for item in items_conceptuels:

                details_par_item[item] = {
                    "exigence_offre": item,
                    "meilleur_match_cv": None,
                    "similarite": 0.0,
                    "seuil": seuil,
                    "couvert": False,
                    "methode": "embeddings"
                }

        else:

            # NOUVEAU : normalisation de la casse avant encodage.
            # Sans cela, "Communication" (offre) vs "communication"
            # (CV) obtient une similarité ~0.999 au lieu de 1.0 : un
            # même mot écrit avec une casse différente est pénalisé
            # artificiellement, ce qui peut faire basculer une
            # compétence sous le seuil dans un cas limite. On encode
            # les versions en minuscules, mais on garde le texte
            # ORIGINAL pour l'affichage dans meilleur_match_cv.

            textes_segments = [
                s["texte"] for s in segments_candidat
            ]

            modele = obtenir_modele_embeddings()

            emb_items = modele.encode(
                [item.lower() for item in items_conceptuels]
            )

            emb_segments = modele.encode(
                [texte.lower() for texte in textes_segments]
            )

            matrice_similarite = cosine_similarity(
                emb_items,
                emb_segments
            )

            for i, item in enumerate(items_conceptuels):

                idx_meilleur = matrice_similarite[i].argmax()

                meilleure_similarite = float(
                    matrice_similarite[i][idx_meilleur]
                )

                meilleur_segment = segments_candidat[idx_meilleur]

                # NOUVEAU : seuil variable selon l'origine du
                # meilleur segment trouvé (voir docstring de la
                # fonction). Un simple mot-clé de compétence déclarée
                # ("competence"), sans contexte, doit être nettement
                # plus proche sémantiquement qu'une phrase
                # d'expérience/poste/formation ("narratif") pour être
                # considéré comme une preuve suffisante.

                seuil_applique = (
                    seuil_competence_seule
                    if meilleur_segment["origine"] == "competence"
                    else seuil
                )

                couvert = (
                    meilleure_similarite >= seuil_applique
                )

                details_par_item[item] = {
                    "exigence_offre": item,
                    "meilleur_match_cv": meilleur_segment["texte"],
                    "similarite": round(meilleure_similarite, 4),
                    "seuil": seuil_applique,
                    "couvert": couvert,
                    "methode": "embeddings",
                    "origine_meilleur_match": meilleur_segment["origine"]
                }

                if MODE_DIAGNOSTIC:

                    statut = "COUVERT" if couvert else "MANQUANT"

                    logger.debug(
                        '  [%s] "%s" -> '
                        'similarité = %.3f (seuil=%.2f, origine=%s) '
                        '(segment : "%s")',
                        statut, item, meilleure_similarite,
                        seuil_applique, meilleur_segment["origine"],
                        meilleur_segment["texte"]
                    )

    # -------------------------------------------------------
    # 3. Recomposition dans l'ordre d'origine
    # -------------------------------------------------------

    items_couverts = []
    items_manquants = []
    details_matching = []

    for item in items_requis:

        detail = details_par_item[item]

        details_matching.append(detail)

        if detail["couvert"]:
            items_couverts.append(item)
        else:
            items_manquants.append(item)

    taux_couverture = (
        len(items_couverts) / len(items_requis)
    )

    return (
        taux_couverture,
        items_couverts,
        items_manquants,
        details_matching
    )


# ---------------------------------------------------------------------------
# 2. Couverture des langues (VERSION CORRIGÉE)
# ---------------------------------------------------------------------------

def _normaliser_texte(texte: str) -> str:

    texte = texte.strip().lower()

    # Uniformise les variantes d'apostrophe ('/’/`) avant tout traitement,
    # pour que "aujourd'hui" et "aujourd’hui" (apostrophe typographique)
    # soient traités comme identiques.
    texte = texte.replace("’", "'").replace("`", "'")

    texte = unicodedata.normalize(
        "NFKD",
        texte
    )

    return "".join(
        c
        for c in texte
        if not unicodedata.combining(c)
    )


# Échelle ordinale unifiée : mappe TOUTES les expressions possibles
# (côté offre ET côté CV) vers un même niveau 1-6.
# Clés triées par longueur décroissante lors du matching pour éviter
# qu'une sous-chaîne courte n'écrase une expression plus précise
# (même logique que _ORDRE_NIVEAUX pour niveau_etudes).
_ORDRE_NIVEAUX_LANGUE = {
    # niveau 1 - débutant
    "debutant": 1, "notions": 1, "a1": 1,

    # niveau 2 - élémentaire
    "elementaire": 2, "a2": 2, "scolaire": 2,

    # niveau 3 - intermédiaire
    "intermediaire": 3, "b1": 3,

    # niveau 4 - avancé / opérationnel
    "avance": 4, "operationnel": 4, "b2": 4, "technique": 4,

    # niveau 5 - courant / professionnel
    "courant": 5, "professionnel": 5, "c1": 5,

    # niveau 6 - bilingue / natif
    "bilingue": 6, "langue maternelle": 6, "maternelle": 6,
    "natif": 6, "native": 6, "c2": 6,
}

# Liste des langues connues, pour extraire le NOM de langue d'une chaîne
# libre côté offre (ex: "Anglais professionnel" -> "anglais").
# À compléter selon les offres rencontrées.
_LANGUES_CONNUES = [
    "francais", "anglais", "espagnol", "allemand", "arabe",
    "italien", "portugais", "chinois", "neerlandais", "russe",
    # NOUVEAU : liste élargie — un profil IT/IA international ne se
    # limite pas aux 10 langues d'origine.
    "japonais", "coreen", "hindi", "turc", "polonais",
    "roumain", "suedois", "norvegien", "danois", "finnois",
    "grec", "hebreu", "ukrainien", "vietnamien", "thai",
    "indonesien", "tagalog", "persan", "urdu", "bengali",
]


# Scores de tests standardisés -> équivalent CECRL, converti ensuite
# vers la même échelle 1-6 via _ORDRE_NIVEAUX_LANGUE.
# (bornes basses indicatives, à ajuster si besoin)
_SEUILS_TOEIC = [(900, "c1"), (785, "b2"), (550, "b1"), (400, "a2")]
_SEUILS_TOEFL = [(95, "c1"), (72, "b2"), (42, "b1")]


def _score_test_vers_niveau(texte_norm: str):
    """Détecte 'toeic 850', 'toefl 90' etc. et renvoie l'équivalent CECRL."""

    match = re.search(r"(toeic|toefl)\D{0,10}(\d{2,3})", texte_norm)
    if not match:
        return None

    test, score = match.group(1), int(match.group(2))
    seuils = _SEUILS_TOEIC if test == "toeic" else _SEUILS_TOEFL

    for borne, niveau_cecrl in seuils:
        if score >= borne:
            return niveau_cecrl

    return "a1"


def _normaliser_niveau_langue(texte: str):
    """
    Retourne un niveau ordinal (1-6), ou None si rien de reconnaissable
    (le texte est vide OU ne contient aucune expression connue).
    """

    if not texte:
        return None

    texte_norm = _normaliser_texte(texte)

    # 1. Score de test chiffré (TOEIC/TOEFL) prioritaire
    equiv_cecrl = _score_test_vers_niveau(texte_norm)
    if equiv_cecrl:
        return _ORDRE_NIVEAUX_LANGUE[equiv_cecrl]

    # 2. Expression connue (mot-clé ou code CECRL)
    for cle in sorted(_ORDRE_NIVEAUX_LANGUE, key=len, reverse=True):
        if cle in texte_norm:
            return _ORDRE_NIVEAUX_LANGUE[cle]

    return None


def _parser_langue_requise(entree):
    """
    Accepte deux formats en entrée pour rester compatible :
    - dict structuré : {"langue": "Anglais", "niveau_requis": "professionnel"}
    - chaîne libre (ancien format offre) : "Anglais professionnel"

    Retourne (nom_langue_normalise, niveau_ordinal_ou_None).
    """

    # niveau_exige_present distingue "pas de niveau demandé" (None normal)
    # de "niveau demandé mais texte non reconnu" (None + flag).
    if isinstance(entree, dict):
        nom = _normaliser_texte(entree.get("langue", ""))
        texte_niveau = entree.get("niveau_requis", "")
        niveau = _normaliser_niveau_langue(texte_niveau)
        niveau_non_reconnu = bool(texte_niveau) and niveau is None
        return nom, niveau, niveau_non_reconnu

    # Chaîne libre : on isole le nom de langue connu, le reste = niveau
    texte_norm = _normaliser_texte(entree)

    nom_trouve = None
    for langue in _LANGUES_CONNUES:
        if langue in texte_norm:
            nom_trouve = langue
            break

    if nom_trouve is None:
        # Aucune langue connue reconnue : on ne peut pas matcher fiablement
        return texte_norm, None, False

    reste = texte_norm.replace(nom_trouve, "").strip()
    niveau = _normaliser_niveau_langue(reste)
    niveau_non_reconnu = bool(reste) and niveau is None

    return nom_trouve, niveau, niveau_non_reconnu


def comparer_niveau_langue(niveau_requis, niveau_candidat) -> float:
    """Même tolérance que comparer_niveau_etudes.

    CORRIGÉ : le cas "niveau candidat non exploitable" retournait
    auparavant 0.5, ce qui pouvait dépasser le score d'un candidat
    ayant explicitement déclaré un niveau bas (ex. A1 requis C1,
    écart=4 -> 0.0). Une absence de preuve ne doit jamais surclasser
    une preuve défavorable connue : le cas est aligné sur le pire cas
    (0.0). La nuance ("non précisé" vs "insuffisant") est portée par
    le flag diagnostique `niveau_non_precise`, pas par le score.
    """

    if niveau_requis is None:
        # Offre ne précise pas de niveau -> la langue seule suffit
        return 1.0

    if niveau_candidat is None:
        # Candidat parle la langue mais aucun niveau exploitable trouvé :
        # score conservateur, jamais meilleur qu'un niveau bas déclaré.
        return 0.0

    if niveau_candidat >= niveau_requis:
        return 1.0

    ecart = niveau_requis - niveau_candidat

    if ecart == 1:
        return 0.5

    return 0.0


def calculer_couverture_langues(langues_requises: list, langues_profil: list):
    """
    Returns:
        (
            taux_couverture,
            langues_couvertes,
            langues_manquantes,
            langues_niveau_non_precise  # langues où le score a été
                                         # abaissé faute de niveau
                                         # candidat exploitable (voir
                                         # comparer_niveau_langue) —
                                         # à distinguer d'un niveau
                                         # explicitement insuffisant.
        )
    """

    if not langues_requises:
        return 1.0, [], [], []

    # Index candidat : nom de langue normalisé -> niveau ordinal
    niveaux_candidat = {}
    for l in langues_profil:
        nom = _normaliser_texte(l.get("langue", ""))
        if not nom:
            continue
        niveaux_candidat[nom] = _normaliser_niveau_langue(l.get("niveau", ""))

    langues_couvertes = []
    langues_manquantes = []
    langues_niveau_non_precise = []
    scores = []

    for langue_requise in langues_requises:

        nom_requis, niveau_requis, niveau_non_reconnu = _parser_langue_requise(
            langue_requise
        )

        if nom_requis not in niveaux_candidat:
            langues_manquantes.append(langue_requise)
            scores.append(0.0)
            continue

        niveau_candidat = niveaux_candidat[nom_requis]

        if niveau_non_reconnu:
            # L'offre exige un niveau mais on n'a pas su l'interpréter :
            # score neutre plutôt qu'un 1.0 (faux "aucune exigence") non mérité.
            score = 0.5
            if MODE_DIAGNOSTIC:
                logger.warning(
                    'Niveau requis non reconnu pour "%s" -> score neutre 0.5',
                    langue_requise,
                )
        else:
            score = comparer_niveau_langue(niveau_requis, niveau_candidat)

            # NOUVEAU : la langue est présente chez le candidat mais
            # aucun niveau exploitable n'a été trouvé -> le score est
            # désormais conservateur (0.0, voir comparer_niveau_langue),
            # mais on le distingue explicitement d'un "insuffisant"
            # avéré pour que l'explication/le recruteur sachent qu'il
            # s'agit d'une info manquante, pas d'une faiblesse prouvée.
            if niveau_requis is not None and niveau_candidat is None:
                langues_niveau_non_precise.append(langue_requise)
                if MODE_DIAGNOSTIC:
                    logger.warning(
                        'Niveau candidat non precise pour "%s" -> '
                        "score conservateur 0.0 (flag niveau_non_precise)",
                        langue_requise,
                    )

        scores.append(score)

        if score >= 0.5:
            langues_couvertes.append(langue_requise)
        else:
            langues_manquantes.append(langue_requise)

        if MODE_DIAGNOSTIC:
            logger.debug(
                '[score=%.2f] langue "%s" (niveau requis=%s) -> '
                'candidat a "%s" (niveau=%s)',
                score, nom_requis, niveau_requis,
                nom_requis, niveau_candidat,
            )

    taux_couverture = sum(scores) / len(langues_requises)

    return (
        taux_couverture,
        langues_couvertes,
        langues_manquantes,
        langues_niveau_non_precise,
    )


# ---------------------------------------------------------------------------
# 3. Niveau d'études
# ---------------------------------------------------------------------------

_ORDRE_NIVEAUX = {

    "bac": 1,

    "bts": 2,
    "dut": 2,
    "bac+2": 2,
    "bac 2": 2,
    "deug": 2,

    "licence": 3,
    "bachelor": 3,
    "bac+3": 3,
    "bac 3": 3,
    "licence professionnelle": 3,
    "bsc": 3,

    "master": 4,
    "ingenieur": 4,
    "bac+5": 4,
    "bac 5": 4,
    "bac+4": 4,
    "bac 4": 4,
    "mba": 4,
    "msc": 4,
    "m2": 4,
    "m1": 4,
    "diplome d ingenieur": 4,

    "doctorat": 5,
    "phd": 5,
    "doctorant": 5,
    "these": 5,
}


def _normaliser_niveau(texte: str):

    if not texte:
        return None

    # NOUVEAU : normalisation accents/casse (via _normaliser_texte) au
    # lieu d'un simple .lower(). Sans ça, "Ingénieur" (accent) ne
    # matchait la clé "ingénieur" QUE si l'accent du CV était
    # identique à celui codé en dur dans le dictionnaire — toute
    # variante d'accentuation ou de casse était silencieusement
    # manquée. Le dictionnaire lui-même n'a donc plus besoin de
    # dupliquer les variantes accentuées ("ingenieur" suffit).
    texte = _normaliser_texte(texte)

    for cle in sorted(
        _ORDRE_NIVEAUX,
        key=len,
        reverse=True
    ):

        if _normaliser_texte(cle) in texte:

            return _ORDRE_NIVEAUX[cle]

    return None


def comparer_niveau_etudes(
    niveau_requis: str,
    formations: list
):
    """
    CORRIGÉ : le cas "aucune formation exploitable trouvée"
    (valeur_candidat == 0) retournait auparavant 0.5, ce qui pouvait
    dépasser le score d'un candidat ayant un diplôme explicitement bas
    (ex. Bac requis Master, écart=3 -> 0.0). Même principe que pour
    les langues : l'absence de preuve ne doit jamais surclasser une
    preuve défavorable connue -> aligné sur 0.0. La nuance est portée
    par le flag retourné, pas par le score.

    Returns:
        (score, niveau_non_precise) — niveau_non_precise est True si
        le score a été abaissé faute de formation exploitable trouvée
        (à distinguer d'un niveau explicitement insuffisant).
    """

    valeur_requise = _normaliser_niveau(
        niveau_requis
    )

    if valeur_requise is None:

        return 1.0, False

    valeur_candidat = 0

    for form in formations:

        v = _normaliser_niveau(
            form.get("intitule", "")
        )

        if v and v > valeur_candidat:

            valeur_candidat = v

    if valeur_candidat == 0:

        return 0.0, True

    if valeur_candidat >= valeur_requise:

        return 1.0, False

    ecart = (
        valeur_requise
        -
        valeur_candidat
    )

    if ecart == 1:

        return 0.5, False

    return 0.0, False


# ---------------------------------------------------------------------------
# 4. Expérience
# ---------------------------------------------------------------------------

# Ensemble fermé d'expressions signifiant "poste toujours occupé
# aujourd'hui". Comparé après normalisation (_normaliser_texte),
# donc pas besoin de dupliquer les variantes accentuées ici.
_SYNONYMES_PRESENT = {
    "present",
    "actuel", "actuelle",
    "aujourd'hui",
    "en cours",
    "a ce jour",
    "maintenant",
    "toujours en poste",
    "poste actuel",
    "",
}


def calculer_annees_experience(
    experiences: list
):

    annee_actuelle = datetime.now().year

    intervalles = []

    nb_ignorees = 0

    for exp in experiences:

        debut_str = str(
            exp.get("date_debut", "")
        )

        fin_str = str(
            exp.get("date_fin", "")
        )

        match_debut = re.search(
            r"\b(19|20)\d{2}\b",
            debut_str
        )

        if not match_debut:

            nb_ignorees += 1

            if MODE_DIAGNOSTIC:

                logger.debug(
                    '[ignorée] expérience "%s" : '
                    'date_debut non parsable ("%s")',
                    exp.get("poste", "?"),
                    debut_str
                )

            continue

        annee_debut = int(
            match_debut.group()
        )

        # NOUVEAU : liste élargie des synonymes de "poste actuel" +
        # normalisation (accents/casse/apostrophes) via _normaliser_texte.
        # Avant : seuls "présent"/"present"/"actuel"/"aujourd'hui" étaient
        # reconnus -> des formulations très courantes en CV français
        # comme "en cours" ou "à ce jour" faisaient perdre l'expérience
        # EN COURS (silencieusement ignorée, alors que c'est souvent la
        # plus significative). Un simple dictionnaire élargi suffit ici
        # (ensemble fermé d'expressions) : pas besoin d'un modèle NLP.
        if _normaliser_texte(fin_str) in _SYNONYMES_PRESENT:

            annee_fin = annee_actuelle

        else:

            match_fin = re.search(
                r"\b(19|20)\d{2}\b",
                fin_str
            )

            if not match_fin:

                nb_ignorees += 1

                if MODE_DIAGNOSTIC:

                    logger.debug(
                        '[ignorée] expérience "%s" : '
                        'date_fin non parsable ("%s")',
                        exp.get("poste", "?"),
                        fin_str
                    )

                continue

            annee_fin = int(
                match_fin.group()
            )

        # CORRIGÉ : était "> annee_debut" (strictement). Une expérience
        # qui commence et finit la MÊME année (ex: stage "2023 → 2023")
        # était silencieusement exclue de tout calcul, sans passer par
        # nb_ignorees -> invisible dans le diagnostic. Elle apporte 0 an
        # (résolution annuelle, pas mensuelle) mais doit être prise en
        # compte, pas disparaître sans trace.
        if annee_fin >= annee_debut:

            intervalles.append(
                (
                    annee_debut,
                    annee_fin
                )
            )

    if (
        experiences
        and
        nb_ignorees == len(experiences)
    ):

        return (
            None,
            nb_ignorees
        )

    if not intervalles:

        return (
            0.0,
            nb_ignorees
        )

    # Fusion des intervalles qui se chevauchent
    intervalles.sort()

    fusionnes = [
        intervalles[0]
    ]

    for debut, fin in intervalles[1:]:

        dernier_debut, dernier_fin = (
            fusionnes[-1]
        )

        if debut <= dernier_fin:

            fusionnes[-1] = (
                dernier_debut,
                max(
                    dernier_fin,
                    fin
                )
            )

        else:

            fusionnes.append(
                (
                    debut,
                    fin
                )
            )

    total_annees = sum(
        fin - debut
        for debut, fin in fusionnes
    )

    return (
        round(total_annees, 1),
        nb_ignorees
    )


def extraire_annees_requises(
    experience_requise_texte: str
):

    if not experience_requise_texte:

        return None

    texte = alpha2digit(
        experience_requise_texte.lower(),
        "fr"
    )

    match = re.search(
        r"(\d+)\s*\+?\s*(ans?|années?)",
        texte
    )

    if match:

        return int(
            match.group(1)
        )

    return None


def calculer_score_experience(
    annees_candidat,
    annees_requises
):
    """
    CORRIGÉ (2 points) :
    1. "if not annees_requises" traitait 0 comme une absence
       d'exigence (0 est "falsy" en Python), alors qu'une offre peut
       explicitement demander "0 an, débutant accepté" — auquel cas
       l'exigence est automatiquement satisfaite (1.0), pas ignorée.
       Distinction faite via "is None" au lieu du test de vérité.
    2. Le cas "annees_candidat non calculable" (dates illisibles)
       retournait 0.5, ce qui pouvait dépasser le score d'un candidat
       ayant explicitement 0-1 an d'expérience. Même principe que
       langues/études : aligné sur 0.0, nuance portée par le flag
       retourné.

    Returns:
        (score, experience_non_precisee)
    """

    if annees_requises is None:

        return None, False

    if annees_requises == 0:

        # Exigence explicitement nulle -> satisfaite d'office.
        return 1.0, False

    if annees_candidat is None:

        return 0.0, True

    return (
        min(
            1.0,
            annees_candidat
            /
            annees_requises
        ),
        False
    )


# ---------------------------------------------------------------------------
# 5. Redistribution des poids
# ---------------------------------------------------------------------------

def redistribuer_poids(
    scores_dimensions: dict,
    poids_initiaux: dict = POIDS_INITIAUX
) -> dict:

    dims_presentes = {

        nom: poids

        for nom, poids
        in poids_initiaux.items()

        if scores_dimensions.get(nom)
        is not None
    }

    poids_total_present = sum(
        dims_presentes.values()
    )

    if poids_total_present == 0:

        return {}

    facteur = (
        1.0
        /
        poids_total_present
    )

    return {

        nom: poids * facteur

        for nom, poids
        in dims_presentes.items()
    }


# ---------------------------------------------------------------------------
# 6. Cap anti-inflation
# ---------------------------------------------------------------------------

def appliquer_cap_anti_inflation(
    score: int,
    taux_couverture_competences: float
):

    if (
        taux_couverture_competences
        <
        SEUIL_CAP_ANTI_INFLATION
        and
        score
        >
        SCORE_CAP_ANTI_INFLATION
    ):

        return (
            SCORE_CAP_ANTI_INFLATION,
            True
        )

    return (
        score,
        False
    )


# ---------------------------------------------------------------------------
# 7. Niveau final
# ---------------------------------------------------------------------------

def deriver_niveau(
    score: int
) -> str:

    if score < 40:

        return "Faible"

    elif score < 60:

        return "Moyen"

    elif score < 75:

        return "Bon"

    elif score < 90:

        return "Très bon"

    else:

        return "Excellent"


# ---------------------------------------------------------------------------
# 8. Explication LLM
# ---------------------------------------------------------------------------

SCHEMA_EXPLICATION_AGENT2 = {

    "type": "object",

    "properties": {

        "points_forts": {
            "type": "array",
            "items": {
                "type": "string"
            }
        },

        "points_manquants": {
            "type": "array",
            "items": {
                "type": "string"
            }
        },

        "explication": {
            "type": "string"
        }
    },

    "required": [
        "points_forts",
        "points_manquants",
        "explication"
    ]
}


PROMPT_AGENT2 = """
Tu es un système de matching CV/poste pour un outil de recrutement
spécialisé IT/IA.

Un score de compatibilité a déjà été calculé par un algorithme
déterministe (moyenne pondérée de 4 dimensions :
couverture des compétences par embeddings+seuil,
couverture des langues, niveau d'études, expérience).

Les compétences/langues déjà identifiées comme "couvertes"
et "manquantes" te sont fournies ci-dessous : elles sont EXACTES
et proviennent d'un calcul automatique fiable.

Ta mission n'est PAS de recalculer le score, ni de modifier,
ni de compléter ces listes avec des éléments non fournis.

1. Reformuler les points_forts et points_manquants fournis
   en phrases claires et naturelles pour un recruteur.

2. Ajouter, si pertinent, un commentaire sur l'adéquation
   de l'expérience du candidat par rapport à l'expérience requise.

3. Rédiger une explication factuelle et neutre qui justifie
   le score obtenu.

Si un plafonnement ("cap anti-inflation") a été appliqué,
mentionne-le explicitement.

Règles strictes :

- N'invente aucune compétence.
- N'invente aucune langue.
- Ne déduis aucune compétence supplémentaire.
- Reste neutre et factuel.
- Tu es un outil d'assistance au recruteur,
  pas une décision finale.
"""


def generer_explication(
    profil,
    offre,
    score,
    niveau,
    competences_couvertes,
    competences_manquantes,
    langues_couvertes,
    langues_manquantes,
    annees_experience_candidat,
    cap_applique,
    langues_niveau_non_precise=None,
    niveau_etudes_non_precise=False,
    experience_non_precisee=False
):

    contexte = (

        PROMPT_AGENT2

        + f"\n\nScore de compatibilité déjà calculé : "
          f"{score}/100 (niveau : {niveau})"

        + (
            f"\n\nATTENTION : le cap anti-inflation "
            f"a été appliqué. Le score a été plafonné "
            f"à {SCORE_CAP_ANTI_INFLATION}/100."
            if cap_applique
            else ""
        )

        + f"\n\nCompétences déjà identifiées comme couvertes : "
          f"{competences_couvertes}"

        + f"\n\nCompétences déjà identifiées comme manquantes : "
          f"{competences_manquantes}"

        + f"\n\nLangues déjà identifiées comme couvertes : "
          f"{langues_couvertes}"

        + f"\n\nLangues déjà identifiées comme manquantes : "
          f"{langues_manquantes}"

        + (
            f"\n\nATTENTION - nuance importante : pour les langues "
            f"suivantes, le candidat mentionne bien parler la langue "
            f"mais AUCUN niveau exploitable n'a été trouvé dans son "
            f"profil (ce n'est PAS un niveau insuffisant constaté, "
            f"c'est une information manquante) : "
            f"{langues_niveau_non_precise}. "
            f"Formule ce point comme 'niveau non précisé, à vérifier "
            f"avec le candidat', jamais comme 'niveau insuffisant'."
            if langues_niveau_non_precise
            else ""
        )

        + (
            f"\n\nATTENTION - nuance importante : aucune formation "
            f"exploitable n'a été trouvée dans le profil du candidat "
            f"pour évaluer son niveau d'études (ce n'est PAS un "
            f"niveau insuffisant constaté, c'est une information "
            f"manquante). Formule ce point comme 'niveau d'études non "
            f"précisé, à vérifier avec le candidat', jamais comme "
            f"'niveau d'études insuffisant'."
            if niveau_etudes_non_precise
            else ""
        )

        + (
            f"\n\nATTENTION - nuance importante : les dates "
            f"d'expérience du candidat n'ont pas pu être calculées "
            f"automatiquement (ce n'est PAS un manque d'expérience "
            f"constaté, c'est une information non exploitable). "
            f"Formule ce point comme 'durée d'expérience non "
            f"calculable automatiquement, à vérifier avec le "
            f"candidat', jamais comme 'expérience insuffisante'."
            if experience_non_precisee
            else ""
        )

        + f"\n\nExpérience du candidat : "
        + (
            f"{annees_experience_candidat} ans"
            if annees_experience_candidat is not None
            else "non calculable automatiquement"
        )

        + f"\n\nExpérience requise par l'offre : "
          f"{offre.get('experience_requise', 'non précisée')}"

        + "\n\nProfil candidat complet :\n"
        + json.dumps(
            profil,
            ensure_ascii=False,
            indent=2
        )

        + "\n\nOffre complète :\n"
        + json.dumps(
            offre,
            ensure_ascii=False,
            indent=2
        )
    )

    return appeler_gemini_json(
        prompt=contexte,
        model="gemini-3.5-flash-lite",
        thinking_level="medium",
        response_schema=SCHEMA_EXPLICATION_AGENT2,
    )


# ---------------------------------------------------------------------------
# 9. Fonction principale
# ---------------------------------------------------------------------------

def calculer_matching(
    profil: dict,
    offre: dict
) -> dict:

    # =========================================================
    # Dimension 1 : compétences
    # =========================================================

    segments_candidat = (
        construire_segments_candidat(
            profil
        )
    )

    competences_techniques_requises = (
        offre.get("competences_techniques_requises") or []
    )

    competences_requises = (

        competences_techniques_requises

        +

        (offre.get(
            "competences_transversales_requises"
        ) or [])
    )

    if MODE_DIAGNOSTIC:

        logger.debug(
            "--- Diagnostic : couverture des compétences ---"
        )

    (
        taux_couverture_competences,
        competences_couvertes,
        competences_manquantes,
        details_matching_competences
    ) = calculer_couverture_competences(

        competences_requises,

        segments_candidat,

        profil.get("competences_techniques") or [],

        items_techniques=competences_techniques_requises
    )

    score_competences = (

        taux_couverture_competences

        if competences_requises

        else None
    )


    # =========================================================
    # Dimension 2 : langues
    # =========================================================

    if MODE_DIAGNOSTIC:

        logger.debug(
            "--- Diagnostic : couverture des langues ---"
        )

    langues_requises = (
        offre.get("langues_requises")
        or []
    )

    (
        taux_couverture_langues,
        langues_couvertes,
        langues_manquantes,
        langues_niveau_non_precise
    ) = calculer_couverture_langues(

        langues_requises,

        profil.get("langues")
        or []
    )

    score_langues = (

        taux_couverture_langues

        if langues_requises

        else None
    )


    # =========================================================
    # Dimension 3 : études
    # =========================================================

    niveau_requis = (
        offre.get(
            "niveau_etudes_requis"
        )
    )

    if niveau_requis:

        (
            score_niveau_etudes,
            niveau_etudes_non_precise
        ) = comparer_niveau_etudes(

            niveau_requis,

            profil.get(
                "formations"
            )
            or []
        )

    else:

        score_niveau_etudes = None
        niveau_etudes_non_precise = False


    # =========================================================
    # Dimension 4 : expérience
    # =========================================================

    (
        annees_experience_candidat,
        nb_experiences_ignorees
    ) = calculer_annees_experience(

        profil.get(
            "experiences"
        )
        or []
    )

    annees_experience_requises = (
        extraire_annees_requises(
            offre.get(
                "experience_requise"
            )
        )
    )

    (
        score_experience,
        experience_non_precisee
    ) = calculer_score_experience(

        annees_experience_candidat,

        annees_experience_requises
    )


    # =========================================================
    # Scores dimensions
    # =========================================================

    scores_dimensions = {

        "competences":
            score_competences,

        "langues":
            score_langues,

        "niveau_etudes":
            score_niveau_etudes,

        "experience":
            score_experience,
    }


    # =========================================================
    # Redistribution
    # =========================================================

    poids_finaux = redistribuer_poids(
        scores_dimensions
    )


    # =========================================================
    # Aucune dimension calculable
    # =========================================================

    if not poids_finaux:

        return {

            "score_compatibilite":
                None,

            "niveau_correspondance":
                "Indéterminé",

            "points_forts":
                [],

            "points_manquants":
                [],

            "explication":
                (
                    "Impossible de calculer un score "
                    "de compatibilité : aucune dimension "
                    "n'est calculable."
                ),

            "_diagnostic": {

                "scores_dimensions":
                    scores_dimensions,

                "annees_experience_candidat":
                    annees_experience_candidat,

                "annees_experience_requises":
                    annees_experience_requises,

                "experiences_ignorees_dates_illisibles":
                    nb_experiences_ignorees,

                "langues_niveau_non_precise":
                    langues_niveau_non_precise,

                "matching_competences_detail":
                    details_matching_competences
            }
        }


    # =========================================================
    # Diagnostic dimensions
    # =========================================================

    if MODE_DIAGNOSTIC:

        logger.debug(
            "--- Diagnostic : dimensions et poids ---"
        )

        for nom in POIDS_INITIAUX:

            logger.debug(
                "%s : score=%s, "
                "poids_final=%.3f",
                nom,
                scores_dimensions.get(nom),
                poids_finaux.get(
                    nom,
                    0
                )
            )


    # =========================================================
    # Score pondéré
    # =========================================================

    score_pondere = sum(

        scores_dimensions[nom]
        * poids

        for nom, poids
        in poids_finaux.items()
    )

    score_brut = round(
        score_pondere * 100
    )


    # =========================================================
    # Cap anti-inflation
    # =========================================================

    couverture_pour_cap = (

        score_competences

        if score_competences
        is not None

        else 1.0
    )

    (
        score_final,
        cap_applique
    ) = appliquer_cap_anti_inflation(

        score_brut,

        couverture_pour_cap
    )

    if MODE_DIAGNOSTIC and cap_applique:

        logger.debug(
            "--- Diagnostic : cap anti-inflation "
            "appliqué (%s -> %s) ---",
            score_brut,
            score_final
        )


    # =========================================================
    # Niveau
    # =========================================================

    niveau = deriver_niveau(
        score_final
    )


    # =========================================================
    # Explication LLM
    # =========================================================

    explication = generer_explication(

        profil,

        offre,

        score_final,

        niveau,

        competences_couvertes=
            competences_couvertes,

        competences_manquantes=
            competences_manquantes,

        langues_couvertes=
            langues_couvertes,

        langues_manquantes=
            langues_manquantes,

        annees_experience_candidat=
            annees_experience_candidat,

        cap_applique=
            cap_applique,

        langues_niveau_non_precise=
            langues_niveau_non_precise,

        niveau_etudes_non_precise=
            niveau_etudes_non_precise,

        experience_non_precisee=
            experience_non_precisee
    )


    # =========================================================
    # Résultat final
    # =========================================================

    return {

        "score_compatibilite":
            score_final,

        "niveau_correspondance":
            niveau,

        "points_forts":
            explication[
                "points_forts"
            ],

        "points_manquants":
            explication[
                "points_manquants"
            ],

        "explication":
            explication[
                "explication"
            ],

        "_diagnostic": {

            "score_brut_avant_cap":
                score_brut,

            "cap_anti_inflation_applique":
                cap_applique,

            "scores_dimensions":
                scores_dimensions,

            "poids_finaux": {

                nom:
                    round(
                        p,
                        4
                    )

                for nom, p
                in poids_finaux.items()
            },

            "annees_experience_candidat":
                annees_experience_candidat,

            "annees_experience_requises":
                annees_experience_requises,

            "experiences_ignorees_dates_illisibles":
                nb_experiences_ignorees,

            # =================================================
            # NOUVEAU
            # =================================================

            "langues_niveau_non_precise":
                langues_niveau_non_precise,

            "niveau_etudes_non_precise":
                niveau_etudes_non_precise,

            "experience_non_precisee":
                experience_non_precisee,

            "matching_competences_detail":
                details_matching_competences
        }
    }