-- db/schema.sql
-- Schema de la base SQLite du copilote recrutement.

PRAGMA foreign_keys = ON;

-- Une session = un depot recruteur (une offre + les CV associes)
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom_offre TEXT NOT NULL,
    date_creation TEXT NOT NULL DEFAULT (datetime('now'))
);

-- L'offre d'emploi liee a une session (texte brut + JSON si extrait structure)
CREATE TABLE IF NOT EXISTS offres (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    texte_brut TEXT NOT NULL,
    json_extrait TEXT,
    parametres_matching TEXT,   -- NOUVEAU : preferences recruteur (JSON), voir db/parametres_offre.py
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
-- Un candidat = un CV traite dans une session
CREATE TABLE IF NOT EXISTS candidats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    nom_fichier TEXT,
    cv_texte TEXT NOT NULL,
    json_extrait TEXT,          -- sortie Agent 1 
    score_matching INTEGER,     -- sortie Agent 2
    niveau_matching TEXT,       -- sortie Agent 2
    json_matching TEXT,         -- sortie complete Agent 2 (points forts/manquants/explication)
    date_creation TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

-- Un entretien = un lien envoye a un candidat, avec un token unique
CREATE TABLE IF NOT EXISTS entretiens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidat_id INTEGER NOT NULL,
    token TEXT NOT NULL UNIQUE,
    statut TEXT NOT NULL DEFAULT 'en_attente',   -- en_attente | repondu
    date_creation TEXT NOT NULL DEFAULT (datetime('now')),
    date_reponse TEXT,
    nb_questions_utilise INTEGER,        -- NOUVEAU (etape 3) : choix recruteur au moment de l'envoi
    niveau_difficulte_utilise TEXT,      -- NOUVEAU (etape 3) : "facile" | "moyen" | "difficile"
    FOREIGN KEY (candidat_id) REFERENCES candidats(id)
);

-- Les questions generees par l'Agent 3 pour un entretien donne
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entretien_id INTEGER NOT NULL,
    texte TEXT NOT NULL,
    type TEXT,                  -- technique | comportementale | situationnelle
    competence_ciblee TEXT,
    justification TEXT,
    ordre INTEGER,               -- pour garder l'ordre d'affichage
    FOREIGN KEY (entretien_id) REFERENCES entretiens(id)
);

-- Les reponses du candidat + evaluation Agent 4
CREATE TABLE IF NOT EXISTS reponses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL UNIQUE,
    texte_reponse TEXT NOT NULL,
    score INTEGER,
    niveau_reponse TEXT,
    points_forts TEXT,           -- JSON (liste) en texte
    axes_amelioration TEXT,      -- JSON (liste) en texte
    feedback TEXT,
    date_creation TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (question_id) REFERENCES questions(id)
);
