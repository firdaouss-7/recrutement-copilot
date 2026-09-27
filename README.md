# Recruitment Copilot — Copilote IA pour le recrutement de profils IT/IA

Copilote intelligent multi-agents qui automatise l'analyse de CV, le matching CV/offre, la génération de questions d'entretien personnalisées (RAG) et l'évaluation des réponses candidats.

## Fonctionnalités

- **Extraction structurée** des CV et offres d'emploi (compétences, expérience, formation, langues) via LLM
- **Matching CV/offre pondéré** par exigence (pas une simple similarité globale), avec mécanisme anti-inflation de score
- **Génération de questions d'entretien** ancrée dans un corpus réel via RAG (FAISS + embeddings)
- **Évaluation automatique** des réponses candidats avec feedback détaillé
- **Espace recruteur** : dépôt de CV, tableau de bord de classement, configuration et envoi des entretiens
- **Espace candidat** : réponse aux questions via un lien à token, envoyé par email

## Architecture

Pipeline de 4 agents orchestrés par **LangGraph** comme un graphe d'états :

| Agent | Rôle |
|---|---|
| Agent 1 — Extraction | Transforme un CV/offre brut en JSON structuré et normalisé |
| Agent 2 — Matching | Calcule un score de correspondance pondéré (compétences, expérience, langues, formation) |
| Agent 3 — Génération (RAG) | Génère des questions d'entretien personnalisées à partir d'un corpus indexé FAISS |
| Agent 4 — Évaluation | Note les réponses du candidat et produit un feedback |

## Stack technique

- **Interface** : Streamlit
- **Orchestration** : LangGraph
- **LLM** : Gemini API (`google-genai`)
- **RAG** : Sentence-Transformers + FAISS
- **Extraction PDF** : pdfplumber / pypdf
- **Traitement linguistique** : pysbd
- **Base de données** : SQLite
- **Email** : SMTP Gmail

## Arborescence

```
recrutement-copilot/
├── app.py                      # Point d'entrée Streamlit
├── agents/
│   ├── agent1_extraction.py    # Extraction CV/offre -> JSON structuré
│   ├── agent2_matching.py      # Calcul du score de matching CV/offre
│   ├── agent3_generation.py    # Génération des questions d'entretien (RAG)
│   └── agent4_evaluation.py    # Évaluation des réponses candidat
├── graph/
│   └── pipeline.py             # Orchestration LangGraph
├── db/
│   ├── db.py                   # Accès base SQLite (CRUD)
│   ├── parametres_offre.py     # Paramètres de matching personnalisables
│   └── schema.sql              # Schéma de la base
├── utils/
│   ├── llm_client.py           # Wrapper d'appel à l'API Gemini
│   └── pdf_reader.py           # Extraction de texte PDF
├── ui/
│   └── components.py           # Composants d'interface réutilisables
├── email_utils/
│   └── envoi.py                # Envoi du lien d'entretien par email
├── data/
│   ├── questions_bank/         # Corpus + index FAISS pour le RAG
│   ├── app_db/                 # Fichier SQLite
│   └── indexer.py              # Construction de l'index FAISS
└── tests/                      # Tests unitaires et fixtures
```

## Installation

```bash
git clone https://github.com/firdaouss-7/recrutement-copilot.git
cd recrutement-copilot
pip install -r requirements.txt
```

## Configuration

Crée un fichier `.env` à la racine avec :

```
GEMINI_API_KEY=ta_clé_api
# + identifiants SMTP Gmail pour l'envoi des liens d'entretien
```

## Lancer l'application

```bash
streamlit run app.py
```

## Auteure

Firdaouss Zai — Élève ingénieure Data Science, Big Data & IA (ENSIASD Taroudant)
Stage réalisé chez 3D Smart Factory, encadré par M. Thierry Bertin
