# db/db.py
#
# Couche d'acces a la base SQLite. Toutes les fonctions ouvrent/ferment
# leur propre connexion (simple et suffisant pour une app Streamlit
# mono-utilisateur cote recruteur).

import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "app_db", "recrutement.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def get_connexion():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # permet d'acceder aux colonnes par nom
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialiser_db():
    """A appeler une fois au demarrage de l'app : cree les tables si absentes."""
    conn = get_connexion()
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def creer_session(nom_offre: str) -> int:
    conn = get_connexion()
    cur = conn.execute(
        "INSERT INTO sessions (nom_offre) VALUES (?)", (nom_offre,)
    )
    conn.commit()
    session_id = cur.lastrowid
    conn.close()
    return session_id


def lister_sessions() -> list[dict]:
    conn = get_connexion()
    rows = conn.execute(
        """SELECT s.*,
                  (SELECT COUNT(*) FROM candidats c WHERE c.session_id = s.id) AS nb_candidats
           FROM sessions s
           ORDER BY s.date_creation DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Offres
# ---------------------------------------------------------------------------

def sauver_offre(session_id: int, texte_brut: str, json_extrait: dict) -> int:
    conn = get_connexion()
    cur = conn.execute(
        "INSERT INTO offres (session_id, texte_brut, json_extrait) VALUES (?, ?, ?)",
        (session_id, texte_brut, json.dumps(json_extrait, ensure_ascii=False)),
    )
    conn.commit()
    offre_id = cur.lastrowid
    conn.close()
    return offre_id


def get_offre_session(session_id: int) -> dict | None:
    conn = get_connexion()
    row = conn.execute(
        "SELECT * FROM offres WHERE session_id = ?", (session_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    d = dict(row)
    d["json_extrait"] = json.loads(d["json_extrait"]) if d["json_extrait"] else None
    return d


# ---------------------------------------------------------------------------
# Candidats
# ---------------------------------------------------------------------------

def sauver_candidat(session_id: int, nom_fichier: str, cv_texte: str, json_extrait: dict) -> int:
    conn = get_connexion()
    cur = conn.execute(
        """INSERT INTO candidats (session_id, nom_fichier, cv_texte, json_extrait)
           VALUES (?, ?, ?, ?)""",
        (session_id, nom_fichier, cv_texte, json.dumps(json_extrait, ensure_ascii=False)),
    )
    conn.commit()
    candidat_id = cur.lastrowid
    conn.close()
    return candidat_id


def sauver_matching(candidat_id: int, score: int, niveau: str, resultat_complet: dict):
    conn = get_connexion()
    conn.execute(
        """UPDATE candidats
           SET score_matching = ?, niveau_matching = ?, json_matching = ?
           WHERE id = ?""",
        (score, niveau, json.dumps(resultat_complet, ensure_ascii=False), candidat_id),
    )
    conn.commit()
    conn.close()


def lister_candidats_session(session_id: int) -> list[dict]:
    conn = get_connexion()
    rows = conn.execute(
        """SELECT * FROM candidats
           WHERE session_id = ?
           ORDER BY score_matching DESC""",
        (session_id,),
    ).fetchall()
    conn.close()
    resultats = []
    for r in rows:
        d = dict(r)
        d["json_extrait"] = json.loads(d["json_extrait"]) if d["json_extrait"] else None
        d["json_matching"] = json.loads(d["json_matching"]) if d["json_matching"] else None
        resultats.append(d)
    return resultats


def get_candidat(candidat_id: int) -> dict | None:
    conn = get_connexion()
    row = conn.execute(
        "SELECT * FROM candidats WHERE id = ?", (candidat_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    d = dict(row)
    d["json_extrait"] = json.loads(d["json_extrait"]) if d["json_extrait"] else None
    d["json_matching"] = json.loads(d["json_matching"]) if d["json_matching"] else None
    return d


# ---------------------------------------------------------------------------
# Entretiens
# ---------------------------------------------------------------------------

def creer_entretien(candidat_id: int, token: str) -> int:
    conn = get_connexion()
    cur = conn.execute(
        "INSERT INTO entretiens (candidat_id, token) VALUES (?, ?)",
        (candidat_id, token),
    )
    conn.commit()
    entretien_id = cur.lastrowid
    conn.close()
    return entretien_id


def get_entretien_par_token(token: str) -> dict | None:
    conn = get_connexion()
    row = conn.execute(
        "SELECT * FROM entretiens WHERE token = ?", (token,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def marquer_entretien_repondu(entretien_id: int):
    conn = get_connexion()
    conn.execute(
        """UPDATE entretiens
           SET statut = 'repondu', date_reponse = datetime('now')
           WHERE id = ?""",
        (entretien_id,),
    )
    conn.commit()
    conn.close()


def get_entretien_par_candidat(candidat_id: int) -> dict | None:
    """Retourne le dernier entretien cree pour ce candidat, ou None si aucun
    entretien n'a encore ete envoye. Sert a savoir, cote dashboard, si le
    bouton "Envoyer l'entretien" doit etre affiche ou remplace par un statut."""
    conn = get_connexion()
    row = conn.execute(
        """SELECT * FROM entretiens
           WHERE candidat_id = ?
           ORDER BY date_creation DESC
           LIMIT 1""",
        (candidat_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def lister_entretiens_session(session_id: int) -> list[dict]:
    conn = get_connexion()
    rows = conn.execute(
        """SELECT e.*, c.nom_fichier, c.score_matching
           FROM entretiens e
           JOIN candidats c ON c.id = e.candidat_id
           WHERE c.session_id = ?
           ORDER BY e.date_creation DESC""",
        (session_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------

def sauver_questions(entretien_id: int, questions: list[dict]):
    """questions : liste de dicts venant de l'Agent 3
    (question, type, competence_ciblee, justification)."""
    conn = get_connexion()
    for i, q in enumerate(questions):
        conn.execute(
            """INSERT INTO questions
               (entretien_id, texte, type, competence_ciblee, justification, ordre)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                entretien_id,
                q["question"],
                q.get("type"),
                q.get("competence_ciblee"),
                q.get("justification"),
                i,
            ),
        )
    conn.commit()
    conn.close()


def lister_questions_entretien(entretien_id: int) -> list[dict]:
    conn = get_connexion()
    rows = conn.execute(
        """SELECT * FROM questions
           WHERE entretien_id = ?
           ORDER BY ordre""",
        (entretien_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Reponses
# ---------------------------------------------------------------------------

def sauver_reponse(question_id: int, texte_reponse: str, evaluation: dict):
    """evaluation : dict venant de l'Agent 4
    (score, niveau_reponse, points_forts, axes_amelioration, feedback)."""
    conn = get_connexion()
    conn.execute(
        """INSERT INTO reponses
           (question_id, texte_reponse, score, niveau_reponse,
            points_forts, axes_amelioration, feedback)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            question_id,
            texte_reponse,
            evaluation["score"],
            evaluation["niveau_reponse"],
            json.dumps(evaluation["points_forts"], ensure_ascii=False),
            json.dumps(evaluation["axes_amelioration"], ensure_ascii=False),
            evaluation["feedback"],
        ),
    )
    conn.commit()
    conn.close()


def lister_reponses_entretien(entretien_id: int) -> list[dict]:
    conn = get_connexion()
    rows = conn.execute(
        """SELECT q.texte AS question, q.type, r.*
           FROM reponses r
           JOIN questions q ON q.id = r.question_id
           WHERE q.entretien_id = ?
           ORDER BY q.ordre""",
        (entretien_id,),
    ).fetchall()
    conn.close()
    resultats = []
    for r in rows:
        d = dict(r)
        d["points_forts"] = json.loads(d["points_forts"]) if d["points_forts"] else []
        d["axes_amelioration"] = json.loads(d["axes_amelioration"]) if d["axes_amelioration"] else []
        resultats.append(d)
    return resultats