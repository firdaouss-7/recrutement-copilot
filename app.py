# app.py
#
# Une seule app Streamlit, deux vues :
#   - Vue recruteur : url normale
#   - Vue candidat   : url + ?token=xxxx

import os
import tempfile

import streamlit as st

from db.db import (
    initialiser_db, creer_session, lister_sessions,
    get_offre_session, lister_candidats_session, get_candidat,
    lister_entretiens_session, get_entretien_par_token,
    lister_questions_entretien, lister_reponses_entretien,
)
from graph.pipeline import (
    traiter_premier_cv, traiter_cv_suivant,
    lancer_entretien, traiter_reponses_candidat,
)
from utils.pdf_reader import extraire_texte_pdf

st.set_page_config(page_title="Copilote Recrutement IT/IA", layout="wide")
initialiser_db()


# ---------------------------------------------------------------------------
# Utilitaire : sauver un fichier uploade dans un fichier temporaire
# ---------------------------------------------------------------------------

def _texte_depuis_upload(fichier_uploade) -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(fichier_uploade.getbuffer())
        chemin_tmp = tmp.name
    try:
        return extraire_texte_pdf(chemin_tmp)
    finally:
        os.remove(chemin_tmp)


# ---------------------------------------------------------------------------
# VUE CANDIDAT (si un token est present dans l'URL)
# ---------------------------------------------------------------------------

def vue_candidat(token: str):
    st.title("Entretien - questions")

    entretien = get_entretien_par_token(token)
    if entretien is None:
        st.error("Lien invalide ou expire.")
        return

    if entretien["statut"] == "repondu":
        st.success("Vous avez deja repondu a ces questions. Merci !")
        return

    questions = lister_questions_entretien(entretien["id"])
    if not questions:
        st.warning("Aucune question disponible pour le moment.")
        return

    st.write("Merci de repondre a chacune des questions ci-dessous.")

    reponses_saisies = {}
    with st.form("form_reponses"):
        for q in questions:
            st.markdown(f"**{q['texte']}**")
            reponses_saisies[q["id"]] = st.text_area(
                "Votre reponse", key=f"reponse_{q['id']}", label_visibility="collapsed"
            )
            st.divider()

        envoye = st.form_submit_button("Envoyer mes reponses")

    if envoye:
        if any(not txt.strip() for txt in reponses_saisies.values()):
            st.error("Merci de repondre a toutes les questions avant d'envoyer.")
            return
        with st.spinner("Envoi en cours..."):
            traiter_reponses_candidat(entretien["id"], reponses_saisies)
        st.success("Vos reponses ont bien ete envoyees. Merci !")


# ---------------------------------------------------------------------------
# VUE RECRUTEUR
# ---------------------------------------------------------------------------

def ecran_accueil():
    st.title("Copilote Recrutement IT/IA")
    st.subheader("Sessions")

    sessions = lister_sessions()
    if not sessions:
        st.info("Aucune session pour le moment.")
    else:
        for s in sessions:
            col1, col2 = st.columns([4, 1])
            col1.write(f"**{s['nom_offre']}** — {s['date_creation']}")
            if col2.button("Ouvrir", key=f"ouvrir_{s['id']}"):
                st.session_state["session_id"] = s["id"]
                st.session_state["ecran"] = "dashboard"
                st.rerun()

    st.divider()
    if st.button("+ Nouvelle session"):
        st.session_state["ecran"] = "nouvelle_session"
        st.rerun()


def ecran_nouvelle_session():
    st.title("Nouvelle session")

    nom_offre = st.text_input("Nom de l'offre (ex: Data Scientist Senior - TechInsight)")
    fichier_offre = st.file_uploader("Offre d'emploi (PDF)", type="pdf")
    fichiers_cv = st.file_uploader("CV des candidats (PDF)", type="pdf", accept_multiple_files=True)

    if st.button("Lancer l'extraction et le matching", type="primary"):
        if not nom_offre or not fichier_offre or not fichiers_cv:
            st.error("Merci de renseigner le nom de l'offre, l'offre et au moins un CV.")
            return

        session_id = creer_session(nom_offre)
        texte_offre = _texte_depuis_upload(fichier_offre)

        barre = st.progress(0.0, text="Traitement en cours...")
        offre_json = None
        for i, fichier_cv in enumerate(fichiers_cv):
            texte_cv = _texte_depuis_upload(fichier_cv)
            barre.progress((i) / len(fichiers_cv), text=f"Traitement de {fichier_cv.name}...")

            if offre_json is None:
                etat = traiter_premier_cv(session_id, texte_offre, fichier_cv.name, texte_cv)
                offre_json = etat["offre_json"]
            else:
                traiter_cv_suivant(session_id, offre_json, fichier_cv.name, texte_cv)

        barre.progress(1.0, text="Termine !")
        st.session_state["session_id"] = session_id
        st.session_state["ecran"] = "dashboard"
        st.rerun()

    if st.button("Annuler"):
        st.session_state["ecran"] = "accueil"
        st.rerun()


def ecran_dashboard():
    session_id = st.session_state["session_id"]
    offre = get_offre_session(session_id)
    candidats = lister_candidats_session(session_id)

    st.title("Dashboard - Classement des candidats")
    if offre and offre.get("json_extrait"):
        st.caption(f"Poste : {offre['json_extrait'].get('titre_poste', offre['json_extrait'].get('titre', 'N/A'))}")

    if not candidats:
        st.info("Aucun candidat dans cette session.")
    else:
        for c in candidats:
            with st.container(border=True):
                col1, col2, col3 = st.columns([3, 1, 1])
                nom_affiche = (c["json_extrait"] or {}).get("nom") or c["nom_fichier"]
                col1.markdown(f"**{nom_affiche}**")
                col2.metric("Score", f"{c['score_matching']}/100" if c["score_matching"] is not None else "—")
                col3.write(c.get("niveau_matching") or "—")

                with st.expander("Details du matching"):
                    jm = c.get("json_matching") or {}
                    st.write("**Points forts :**", jm.get("points_forts", []))
                    st.write("**Points manquants :**", jm.get("points_manquants", []))
                    st.write(jm.get("explication", ""))

                email_candidat = st.text_input(
                    "Email du candidat", key=f"email_{c['id']}", placeholder="candidat@exemple.com"
                )
                if st.button("Envoyer entretien", key=f"envoyer_{c['id']}"):
                    if not email_candidat:
                        st.error("Merci de renseigner l'email du candidat.")
                    else:
                        with st.spinner("Generation des questions et envoi de l'email..."):
                            lancer_entretien(c, offre["json_extrait"], email_candidat)
                        st.success(f"Entretien envoye a {nom_affiche} !")

    st.divider()
    if st.button("Voir les resultats d'entretiens"):
        st.session_state["ecran"] = "resultats"
        st.rerun()
    if st.button("Retour a l'accueil"):
        st.session_state["ecran"] = "accueil"
        st.rerun()


def ecran_resultats():
    session_id = st.session_state["session_id"]
    st.title("Resultats des entretiens")

    if st.button("Actualiser"):
        st.rerun()

    entretiens = lister_entretiens_session(session_id)
    if not entretiens:
        st.info("Aucun entretien envoye pour le moment.")
    else:
        for e in entretiens:
            with st.container(border=True):
                col1, col2, col3 = st.columns([3, 1, 1])
                col1.markdown(f"**{e['nom_fichier']}**")
                col2.write(f"Matching : {e['score_matching']}/100" if e["score_matching"] is not None else "—")
                statut_affiche = "✅ Repondu" if e["statut"] == "repondu" else "⏳ En attente"
                col3.write(statut_affiche)

                if e["statut"] == "repondu":
                    reponses = lister_reponses_entretien(e["id"])
                    with st.expander("Voir les reponses et evaluations"):
                        for r in reponses:
                            st.markdown(f"**Q : {r['question']}**")
                            st.write(f"Reponse : {r['texte_reponse']}")
                            st.write(f"Score : {r['score']}/100 — {r['niveau_reponse']}")
                            st.write("Points forts :", r["points_forts"])
                            st.write("Axes d'amelioration :", r["axes_amelioration"])
                            st.caption(r["feedback"])
                            st.divider()

    st.divider()
    if st.button("Retour au dashboard"):
        st.session_state["ecran"] = "dashboard"
        st.rerun()


def vue_recruteur():
    if "ecran" not in st.session_state:
        st.session_state["ecran"] = "accueil"

    ecran = st.session_state["ecran"]
    if ecran == "accueil":
        ecran_accueil()
    elif ecran == "nouvelle_session":
        ecran_nouvelle_session()
    elif ecran == "dashboard":
        ecran_dashboard()
    elif ecran == "resultats":
        ecran_resultats()
    else:
        ecran_accueil()


# ---------------------------------------------------------------------------
# Point d'entree : bascule vue recruteur / vue candidat selon l'URL
# ---------------------------------------------------------------------------

token = st.query_params.get("token")
if token:
    vue_candidat(token)
else:
    vue_recruteur()