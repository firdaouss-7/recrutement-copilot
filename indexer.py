# indexer.py
#
# Etape E du plan Agent 3 : construit l'index FAISS a partir du corpus
# de questions (data/questions_bank/corpus_final.json).
#
# A lancer UNE SEULE FOIS (ou a chaque fois que corpus_final.json change),
# pas a chaque appel de l'Agent 3. Produit 2 fichiers dans
# data/questions_bank/ :
#   - corpus_index.faiss    : les vecteurs (embeddings) des questions
#   - corpus_metadata.json  : les metadonnees (id, texte, type, domaine)
#     dans le MEME ORDRE que les vecteurs, pour retrouver le texte
#     correspondant a un resultat de recherche FAISS (qui ne renvoie
#     que des indices numeriques).
#
# Usage :
#   python indexer.py

import json
import logging

import faiss
from sentence_transformers import SentenceTransformer

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

CORPUS_PATH = "data/questions_bank/corpus_final.json"
INDEX_PATH = "data/questions_bank/corpus_index.faiss"
METADATA_PATH = "data/questions_bank/corpus_metadata.json"

# Meme modele que l'Agent 2, pour rester coherent sur tout le pipeline.
NOM_MODELE_EMBEDDINGS = "paraphrase-multilingual-MiniLM-L12-v2"


def construire_index():
    """
    Construit l'index vectoriel FAISS a partir du corpus de questions.

    Lit corpus_final.json, encode chaque question en vecteur (embeddings),
    puis ecrit l'index FAISS et les metadonnees associees sur disque.
    Ne prend aucun argument et n'a pas de valeur de retour : effet de bord
    uniquement (fichiers ecrits dans data/questions_bank/).
    """
    with open(CORPUS_PATH, "r", encoding="utf-8") as f:
        corpus = json.load(f)

    logger.info("Chargement de %d questions depuis %s...", len(corpus), CORPUS_PATH)

    logger.info("Chargement du modele d'embeddings (%s)...", NOM_MODELE_EMBEDDINGS)
    modele = SentenceTransformer(NOM_MODELE_EMBEDDINGS)

    textes = [q["texte"] for q in corpus]

    logger.info("Encodage des questions en vecteurs...")
    embeddings = modele.encode(
        textes,
        show_progress_bar=True,
        convert_to_numpy=True,
    )

    # Normalisation L2 : permet d'utiliser un index Inner Product (IP)
    # pour obtenir directement une similarite cosinus lors des recherches.
    faiss.normalize_L2(embeddings)

    dimension = embeddings.shape[1]
    index = faiss.IndexFlatIP(dimension)
    index.add(embeddings)

    faiss.write_index(index, INDEX_PATH)

    # corpus_metadata.json = copie du corpus, dans le MEME ordre que
    # les vecteurs ajoutes a l'index (index FAISS i <-> corpus[i]).
    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(corpus, f, ensure_ascii=False, indent=2)

    logger.info(
        "Index FAISS cree : %d vecteurs, dimension %d.",
        index.ntotal,
        dimension,
    )
    logger.info("Fichiers generes :")
    logger.info(" - %s", INDEX_PATH)
    logger.info(" - %s", METADATA_PATH)


if __name__ == "__main__":
    construire_index()