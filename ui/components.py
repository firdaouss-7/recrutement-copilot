# ui/components.py
#
# Bibliotheque interne de composants d'interface : injection du style
# global (une seule fois par page) + petites fabriques de HTML pour
# remplacer les rendus "bruts" (listes Python, JSON, emojis) par des
# elements visuels sobres et coherents (badges, puces, barre de score).
#
# Convention : toute fonction qui retourne du HTML doit etre affichee
# avec st.markdown(..., unsafe_allow_html=True). Rien ici ne doit
# contenir de donnees non echappees (utiliser html.escape).

from __future__ import annotations

import html as _html
import unicodedata

import streamlit as st

# ---------------------------------------------------------------------------
# Helpers internes
# ---------------------------------------------------------------------------


def _normaliser(texte: str | None) -> str:
    """Normalise une chaine (minuscules, sans accents) pour comparer les
    libelles de niveau de facon fiable (voir _NIVEAU_TONE)."""
    if not texte:
        return ""
    sans_accents = "".join(
        c for c in unicodedata.normalize("NFKD", texte) if not unicodedata.combining(c)
    )
    return sans_accents.strip().lower()


def _e(texte) -> str:
    """Echappe une valeur pour insertion sure dans du HTML (evite toute
    injection via un champ libre venant du LLM ou du candidat)."""
    return _html.escape(str(texte)) if texte is not None else ""


# Palette semantique partagee entre les niveaux de matching (Agent 2)
# et les niveaux de reponse (Agent 4) : memes libelles, meme code couleur.
_NIVEAU_TONE = {
    "faible": "danger",
    "insuffisant": "danger",
    "moyen": "warning",
    "bon": "info",
    "tres bon": "accent",
    "excellent": "success",
}

_TONE_COLORS = {
    "success": ("#15803D", "#ECFDF3", "#B7E4C7"),
    "info": ("#1D4ED8", "#EFF4FF", "#BFD7FF"),
    "accent": ("#0E7490", "#ECFCFF", "#B7EEF7"),
    "warning": ("#B45309", "#FFF7E6", "#F6DDA8"),
    "danger": ("#B91C1C", "#FEF1F1", "#F3C6C6"),
    "neutral": ("#475569", "#F1F5F9", "#E1E7EF"),
}


def tone_pour_niveau(niveau: str | None) -> str:
    """Associe un niveau qualitatif (matching ou reponse) a une teinte
    semantique (success/info/warning/danger...) pour l'affichage."""
    return _NIVEAU_TONE.get(_normaliser(niveau), "neutral")


# ---------------------------------------------------------------------------
# Style global (a appeler une seule fois, tout en haut de app.py)
# ---------------------------------------------------------------------------

def injecter_style() -> None:
    """Injecte le CSS global de l'application (une seule fois, en haut de
    app.py) : polices, couleurs, cartes, badges, barre de score, etc."""
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

        html, body, [class*="css"], .stApp, button, input, textarea, select {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
        }

        .stApp { background: #F7F8FA; }
        #MainMenu, footer, header[data-testid="stHeader"] { background: transparent; }

        /* --- Conteneur principal ------------------------------------- */
        .block-container { padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1080px; }

        /* --- Sidebar ---------------------------------------------------- */
        section[data-testid="stSidebar"] {
            background: #12172B;
            border-right: 1px solid #1E2440;
        }
        section[data-testid="stSidebar"] * { color: #E3E6F0 !important; }
        section[data-testid="stSidebar"] .stButton > button {
            width: 100%;
            text-align: left;
            background: transparent;
            border: 1px solid transparent;
            border-radius: 8px;
            padding: 0.55rem 0.85rem;
            font-weight: 500;
            font-size: 0.92rem;
            transition: background 0.15s ease, border-color 0.15s ease;
        }
        section[data-testid="stSidebar"] .stButton > button:hover {
            background: #1C2340;
            border-color: #2A3160;
        }
        section[data-testid="stSidebar"] .stButton > button[kind="primary"] {
            background: #4338CA;
            border-color: #4338CA;
        }
        section[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
            background: #372DB0;
        }

        /* --- Titres ------------------------------------------------------ */
        h1 { font-weight: 800 !important; letter-spacing: -0.02em; color: #0F172A; }
        h2, h3 { font-weight: 700 !important; letter-spacing: -0.01em; color: #0F172A; }
        .app-eyebrow {
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-size: 0.72rem;
            font-weight: 700;
            color: #6366F1;
            margin-bottom: 0.15rem;
        }
        .app-subtitle { color: #64748B; font-size: 0.95rem; margin-top: -0.6rem; margin-bottom: 1.4rem; }

        /* --- Boutons (zone principale) ------------------------------- */
        .stButton > button {
            border-radius: 8px;
            font-weight: 600;
            padding: 0.5rem 1.1rem;
            border: 1px solid #E2E8F0;
            transition: transform 0.05s ease, box-shadow 0.15s ease;
        }
        .stButton > button:hover { box-shadow: 0 4px 10px rgba(15, 23, 42, 0.08); }
        .stButton > button:active { transform: translateY(1px); }
        .stButton > button[kind="primary"] {
            background: linear-gradient(180deg, #4F46E5 0%, #4338CA 100%);
            border: none;
            box-shadow: 0 1px 2px rgba(67, 56, 202, 0.35);
        }
        .stButton > button[kind="primary"]:hover { box-shadow: 0 6px 14px rgba(67, 56, 202, 0.32); }
        .stButton > button[kind="secondary"] { background: #FFFFFF; color: #334155; }

        /* --- Cartes generiques (st.container(key=...)) ---------------- */
        div[class*="st-key-carte-"] {
            background: #FFFFFF;
            border: 1px solid #E7EAF1;
            border-radius: 14px;
            padding: 1.35rem 1.5rem 1.15rem 1.5rem;
            margin-bottom: 1rem;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
        }
        div[class*="st-key-kpi-"] {
            background: #FFFFFF;
            border: 1px solid #E7EAF1;
            border-radius: 14px;
            padding: 1rem 1.2rem;
        }
        div[class*="st-key-qa-"] {
            background: #FBFBFD;
            border: 1px solid #ECEEF3;
            border-radius: 12px;
            padding: 1.1rem 1.3rem;
            margin-bottom: 0.85rem;
        }

        /* --- Score : label + piste + remplissage ----------------------- */
        .score-row { display: flex; align-items: baseline; gap: 0.6rem; margin-bottom: 0.4rem; }
        .score-value { font-size: 1.35rem; font-weight: 800; letter-spacing: -0.01em; }
        .score-track {
            width: 100%; height: 8px; border-radius: 999px;
            background: #EEF0F5; overflow: hidden;
        }
        .score-fill { height: 100%; border-radius: 999px; }

        /* --- Badges (statut, niveau) ------------------------------------ */
        .badge {
            display: inline-block; padding: 0.18rem 0.65rem; border-radius: 999px;
            font-size: 0.76rem; font-weight: 700; letter-spacing: 0.01em;
            border: 1px solid transparent; white-space: nowrap;
        }

        /* --- Puces (points forts / manquants) --------------------------- */
        .chip-group { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.35rem 0 0.1rem 0; }
        .chip {
            display: inline-flex; align-items: center; gap: 0.3rem;
            padding: 0.28rem 0.7rem; border-radius: 8px;
            font-size: 0.82rem; font-weight: 500; border: 1px solid transparent;
        }
        .chip-empty { color: #94A3B8; font-size: 0.85rem; font-style: italic; margin: 0.3rem 0; }
        .section-label {
            font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
            letter-spacing: 0.06em; color: #94A3B8; margin: 0.9rem 0 0.15rem 0;
        }

        /* --- Champs de formulaire ---------------------------------------- */
        .stTextInput > div > div, .stTextArea > div > div {
            border-radius: 8px !important;
        }
        [data-testid="stFileUploaderDropzone"] {
            border-radius: 12px; border: 1.5px dashed #C7CDE0; background: #FAFBFD;
        }

        hr { border-color: #E7EAF1; }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Composants
# ---------------------------------------------------------------------------

def en_tete(eyebrow: str, titre: str, sous_titre: str | None = None) -> None:
    """Affiche l'en-tete standard d'un ecran : petit libelle (eyebrow),
    titre principal, et sous-titre optionnel."""
    st.markdown(f'<div class="app-eyebrow">{_e(eyebrow)}</div>', unsafe_allow_html=True)
    st.title(titre)
    if sous_titre:
        st.markdown(f'<div class="app-subtitle">{_e(sous_titre)}</div>', unsafe_allow_html=True)


def badge(texte: str, tone: str = "neutral") -> str:
    """Retourne le HTML d'un badge colore (pastille arrondie) pour le
    texte et la teinte semantique donnes."""
    couleur, fond, bordure = _TONE_COLORS.get(tone, _TONE_COLORS["neutral"])
    return (
        f'<span class="badge" style="color:{couleur}; background:{fond}; '
        f'border-color:{bordure};">{_e(texte)}</span>'
    )


def badge_niveau(niveau: str | None) -> str:
    """Retourne le HTML d'un badge de niveau (matching ou reponse), avec
    la teinte semantique associee automatiquement (voir tone_pour_niveau)."""
    if not niveau:
        return badge("Non evalue", "neutral")
    return badge(niveau, tone_pour_niveau(niveau))


def badge_statut_entretien(statut: str) -> str:
    """Retourne le HTML du badge de statut d'un entretien
    ("Reponse recue" en vert, ou "En attente de reponse" en orange)."""
    if statut == "repondu":
        return badge("Reponse recue", "success")
    return badge("En attente de reponse", "warning")


def barre_score(score: int | None, niveau: str | None = None) -> str:
    """Retourne le HTML d'une barre de score (valeur numerique + piste
    remplie proportionnellement), coloree selon le niveau qualitatif."""
    valeur = 0 if score is None else max(0, min(100, score))
    tone = tone_pour_niveau(niveau) if niveau else "info"
    couleur, _, _ = _TONE_COLORS.get(tone, _TONE_COLORS["info"])
    label = "Score non disponible" if score is None else f"{valeur}/100"
    return f"""
    <div>
      <div class="score-row">
        <span class="score-value" style="color:{couleur};">{_e(label)}</span>
        {badge_niveau(niveau) if niveau else ""}
      </div>
      <div class="score-track">
        <div class="score-fill" style="width:{valeur}%; background:{couleur};"></div>
      </div>
    </div>
    """


def liste_chips(items: list, tone: str = "neutral") -> str:
    """Retourne le HTML d'une liste de puces colorees (ex. points forts /
    manquants) a partir d'une liste de chaines. Affiche un message neutre
    si la liste est vide."""
    couleur, fond, bordure = _TONE_COLORS.get(tone, _TONE_COLORS["neutral"])
    if not items:
        return '<div class="chip-empty">Aucun element identifie.</div>'
    puces = "".join(
        f'<span class="chip" style="color:{couleur}; background:{fond}; '
        f'border-color:{bordure};">{_e(item)}</span>'
        for item in items
    )
    return f'<div class="chip-group">{puces}</div>'


def etiquette_section(texte: str) -> str:
    """Retourne le HTML d'un petit libelle de section (majuscules,
    espacement large) utilise au-dessus d'un bloc de contenu."""
    return f'<div class="section-label">{_e(texte)}</div>'
