# app.py
#
# Une seule app Streamlit, deux vues :
#   - Vue recruteur : url normale (navigation par sidebar)
#   - Vue candidat   : url + ?token=xxxx

import os
import tempfile

import streamlit as st

from db.db import (
    initialiser_db, creer_session, lister_sessions,
    get_offre_session, lister_candidats_session, get_candidat,
    lister_entretiens_session, get_entretien_par_token,
    get_entretien_par_candidat,
    lister_questions_entretien, lister_reponses_entretien,
)
from graph.pipeline import (
    traiter_premier_cv, traiter_cv_suivant,
    lancer_entretien, traiter_reponses_candidat,
)
from utils.pdf_reader import extraire_texte_pdf
from ui.components import (
    injecter_style, en_tete, badge, badge_statut_entretien,
    barre_score, liste_chips, etiquette_section,
)

st.set_page_config(page_title="Copilote Recrutement IT/IA", layout="wide")
initialiser_db()
injecter_style()


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


def _email_extrait(candidat: dict) -> str:
    """Recupere l'email deja trouve par l'Agent 1 dans le CV, s'il existe."""
    profil = candidat.get("json_extrait") or {}
    contact = profil.get("contact") or {}
    return contact.get("email") or ""


# ---------------------------------------------------------------------------
# VUE CANDIDAT (si un token est present dans l'URL)
# ---------------------------------------------------------------------------

def vue_candidat(token: str):
    st.markdown(
        '<div class="app-eyebrow">Entretien</div>', unsafe_allow_html=True
    )
    st.title("Vos questions d'entretien")

    entretien = get_entretien_par_token(token)
    if entretien is None:
        st.error("Ce lien est invalide ou a expire.")
        return

    if entretien["statut"] == "repondu":
        st.success("Vous avez deja repondu a ces questions. Merci, votre candidature est bien enregistree.")
        return

    questions = lister_questions_entretien(entretien["id"])
    if not questions:
        st.warning("Aucune question n'est disponible pour le moment. Merci de reessayer plus tard.")
        return

    st.markdown(
        '<div class="app-subtitle">Merci de repondre a chacune des questions ci-dessous avec autant '
        'de precision que possible. Vos reponses seront analysees automatiquement.</div>',
        unsafe_allow_html=True,
    )

    reponses_saisies = {}
    with st.form("form_reponses"):
        for i, q in enumerate(questions, start=1):
            with st.container(key=f"carte-question-{q['id']}"):
                st.markdown(
                    f'<div class="section-label">Question {i}/{len(questions)}'
                    f'{"  &middot;  " + q["type"] if q.get("type") else ""}</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(f"**{q['texte']}**")
                reponses_saisies[q["id"]] = st.text_area(
                    "Votre reponse",
                    key=f"reponse_{q['id']}",
                    label_visibility="collapsed",
                    placeholder="Redigez votre reponse ici...",
                    height=120,
                )

        envoye = st.form_submit_button("Envoyer mes reponses", type="primary")

    if envoye:
        if any(not txt.strip() for txt in reponses_saisies.values()):
            st.error("Merci de repondre a toutes les questions avant d'envoyer.")
            return
        with st.spinner("Envoi en cours..."):
            traiter_reponses_candidat(entretien["id"], reponses_saisies)
        st.success("Vos reponses ont bien ete envoyees. Merci !")


# ---------------------------------------------------------------------------
# NAVIGATION (sidebar)
# ---------------------------------------------------------------------------

def barre_navigation():
    with st.sidebar:
        st.markdown(
            '<div style="padding: 0.3rem 0 1.1rem 0;">'
            '<div style="font-weight:800; font-size:1.05rem; letter-spacing:-0.01em;">Copilote Recrutement</div>'
            '<div style="font-size:0.78rem; color:#8B90A8; margin-top:0.1rem;">Espace recruteur &middot; IT / IA</div>'
            '</div>',
            unsafe_allow_html=True,
        )

        ecran = st.session_state.get("ecran", "accueil")

        if st.button(
            "Sessions", key="nav_accueil",
            type="primary" if ecran in ("accueil", "nouvelle_session") else "secondary",
        ):
            st.session_state["ecran"] = "accueil"
            st.rerun()

        if "session_id" in st.session_state:
            offre = get_offre_session(st.session_state["session_id"])
            nom_offre = None
            if offre and offre.get("json_extrait"):
                nom_offre = offre["json_extrait"].get("titre_poste") or offre["json_extrait"].get("titre")

            st.markdown(
                '<div class="section-label" style="margin-top:1.1rem;">Session en cours</div>'
                f'<div style="font-size:0.86rem; color:#C7CBE0; margin-bottom:0.6rem;">{nom_offre or "Offre sans titre"}</div>',
                unsafe_allow_html=True,
            )

            if st.button(
                "Tableau de bord", key="nav_dashboard",
                type="primary" if ecran == "dashboard" else "secondary",
            ):
                st.session_state["ecran"] = "dashboard"
                st.rerun()

            if st.button(
                "Resultats d'entretiens", key="nav_resultats",
                type="primary" if ecran == "resultats" else "secondary",
            ):
                st.session_state["ecran"] = "resultats"
                st.rerun()


# ---------------------------------------------------------------------------
# VUE RECRUTEUR
# ---------------------------------------------------------------------------

def ecran_accueil():
    en_tete("Espace recruteur", "Sessions de recrutement", "Retrouvez vos campagnes en cours ou lancez-en une nouvelle.")

    sessions = lister_sessions()
    if not sessions:
        st.info("Aucune session pour le moment. Creez votre premiere session pour commencer.")
    else:
        for s in sessions:
            with st.container(key=f"carte-session-{s['id']}"):
                col1, col2 = st.columns([5, 1])
                with col1:
                    st.markdown(f"**{s['nom_offre']}**")
                    nb = s.get("nb_candidats", 0)
                    st.markdown(
                        f'<span style="color:#64748B; font-size:0.85rem;">'
                        f'{s["date_creation"]} &middot; {nb} candidat{"s" if nb != 1 else ""}</span>',
                        unsafe_allow_html=True,
                    )
                with col2:
                    if st.button("Ouvrir", key=f"ouvrir_{s['id']}", type="secondary"):
                        st.session_state["session_id"] = s["id"]
                        st.session_state["ecran"] = "dashboard"
                        st.rerun()

    st.write("")
    if st.button("+ Nouvelle session", type="primary"):
        st.session_state["ecran"] = "nouvelle_session"
        st.rerun()


def ecran_nouvelle_session():
    en_tete("Nouvelle campagne", "Deposer une offre et des CV", "L'extraction et le matching se lancent automatiquement pour chaque candidat.")

    with st.container(key="carte-nouvelle-session"):
        st.markdown(etiquette_section("Intitule de l'offre"), unsafe_allow_html=True)
        nom_offre = st.text_input(
            "Nom de l'offre", label_visibility="collapsed",
            placeholder="Ex. Data Scientist Senior - TechInsight",
        )

        st.markdown(etiquette_section("Offre d'emploi (PDF)"), unsafe_allow_html=True)
        fichier_offre = st.file_uploader("Offre d'emploi (PDF)", type="pdf", label_visibility="collapsed")

        st.markdown(etiquette_section("CV des candidats (PDF)"), unsafe_allow_html=True)
        fichiers_cv = st.file_uploader(
            "CV des candidats (PDF)", type="pdf", accept_multiple_files=True, label_visibility="collapsed"
        )

        col1, col2 = st.columns([1, 5])
        with col1:
            lancer = st.button("Lancer l'analyse", type="primary")
        with col2:
            annuler = st.button("Annuler", type="secondary")

    if lancer:
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

    if annuler:
        st.session_state["ecran"] = "accueil"
        st.rerun()


def ecran_dashboard():
    session_id = st.session_state["session_id"]
    offre = get_offre_session(session_id)
    candidats = lister_candidats_session(session_id)

    titre_offre = "Offre sans titre"
    if offre and offre.get("json_extrait"):
        titre_offre = offre["json_extrait"].get("titre_poste") or offre["json_extrait"].get("titre") or titre_offre

    en_tete("Tableau de bord", "Classement des candidats", titre_offre)

    if not candidats:
        st.info("Aucun candidat dans cette session.")
        return

    scores_valides = [c["score_matching"] for c in candidats if c["score_matching"] is not None]
    score_moyen = round(sum(scores_valides) / len(scores_valides)) if scores_valides else None

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        with st.container(key="kpi-candidats"):
            st.markdown(etiquette_section("Candidats"), unsafe_allow_html=True)
            st.markdown(f'<div class="score-value" style="color:#0F172A;">{len(candidats)}</div>', unsafe_allow_html=True)
    with col_b:
        with st.container(key="kpi-score-moyen"):
            st.markdown(etiquette_section("Score moyen"), unsafe_allow_html=True)
            st.markdown(
                f'<div class="score-value" style="color:#0F172A;">{score_moyen if score_moyen is not None else "-"}/100</div>',
                unsafe_allow_html=True,
            )
    with col_c:
        with st.container(key="kpi-entretiens"):
            nb_envoyes = sum(1 for c in candidats if get_entretien_par_candidat(c["id"]))
            st.markdown(etiquette_section("Entretiens envoyes"), unsafe_allow_html=True)
            st.markdown(f'<div class="score-value" style="color:#0F172A;">{nb_envoyes}</div>', unsafe_allow_html=True)

    st.write("")

    for c in candidats:
        with st.container(key=f"carte-candidat-{c['id']}"):
            nom_affiche = (c["json_extrait"] or {}).get("nom") or c["nom_fichier"]
            titre_pro = (c["json_extrait"] or {}).get("titre_professionnel")

            col1, col2 = st.columns([3, 2])
            with col1:
                st.markdown(f"### {nom_affiche}")
                if titre_pro:
                    st.markdown(f'<span style="color:#64748B; font-size:0.9rem;">{titre_pro}</span>', unsafe_allow_html=True)
            with col2:
                st.markdown(barre_score(c["score_matching"], c.get("niveau_matching")), unsafe_allow_html=True)

            with st.expander("Voir le detail du matching"):
                jm = c.get("json_matching") or {}
                st.markdown(etiquette_section("Points forts"), unsafe_allow_html=True)
                st.markdown(liste_chips(jm.get("points_forts", []), tone="success"), unsafe_allow_html=True)

                st.markdown(etiquette_section("Points manquants"), unsafe_allow_html=True)
                st.markdown(liste_chips(jm.get("points_manquants", []), tone="warning"), unsafe_allow_html=True)

                if jm.get("explication"):
                    st.markdown(etiquette_section("Analyse"), unsafe_allow_html=True)
                    st.write(jm["explication"])

            st.markdown('<div style="height:0.4rem;"></div>', unsafe_allow_html=True)

            entretien_existant = get_entretien_par_candidat(c["id"])
            if entretien_existant:
                col_statut, col_action = st.columns([3, 2])
                with col_statut:
                    st.markdown(
                        etiquette_section("Entretien") + badge_statut_entretien(entretien_existant["statut"]),
                        unsafe_allow_html=True,
                    )
                with col_action:
                    if entretien_existant["statut"] != "repondu":
                        if st.button("Renvoyer le lien", key=f"renvoyer_{c['id']}", type="secondary"):
                            st.session_state[f"afficher_envoi_{c['id']}"] = True
            else:
                if st.button("Envoyer l'entretien", key=f"envoyer_bouton_{c['id']}", type="primary"):
                    st.session_state[f"afficher_envoi_{c['id']}"] = True

            if st.session_state.get(f"afficher_envoi_{c['id']}"):
                email_defaut = _email_extrait(c)
                st.markdown(etiquette_section("Adresse email du candidat"), unsafe_allow_html=True)
                if email_defaut:
                    st.caption("Adresse recuperee automatiquement depuis le CV — modifiable si besoin.")
                else:
                    st.caption("Aucune adresse n'a ete trouvee dans le CV : merci de la renseigner.")
                email_candidat = st.text_input(
                    "Email du candidat", value=email_defaut, key=f"email_{c['id']}",
                    label_visibility="collapsed", placeholder="candidat@exemple.com",
                )
                if st.button("Confirmer l'envoi", key=f"confirmer_envoi_{c['id']}", type="primary"):
                    if not email_candidat:
                        st.error("Merci de renseigner l'email du candidat.")
                    else:
                        with st.spinner("Generation des questions et envoi de l'email..."):
                            lancer_entretien(c, offre["json_extrait"], email_candidat)
                        st.session_state[f"afficher_envoi_{c['id']}"] = False
                        st.success(f"Entretien envoye a {nom_affiche}.")
                        st.rerun()


def ecran_resultats():
    session_id = st.session_state["session_id"]
    en_tete("Suivi", "Resultats des entretiens", "Consultez les reponses et evaluations generees par l'Agent 4.")

    if st.button("Actualiser", type="secondary"):
        st.rerun()

    entretiens = lister_entretiens_session(session_id)
    if not entretiens:
        st.info("Aucun entretien envoye pour le moment.")
        return

    for e in entretiens:
        with st.container(key=f"carte-entretien-{e['id']}"):
            col1, col2, col3 = st.columns([3, 2, 2])
            with col1:
                st.markdown(f"**{e['nom_fichier']}**")
            with col2:
                st.markdown(
                    f'Matching&nbsp;: <strong>{e["score_matching"]}/100</strong>'
                    if e["score_matching"] is not None else "Matching : -",
                    unsafe_allow_html=True,
                )
            with col3:
                st.markdown(badge_statut_entretien(e["statut"]), unsafe_allow_html=True)

            if e["statut"] == "repondu":
                reponses = lister_reponses_entretien(e["id"])
                with st.expander("Voir les reponses et evaluations"):
                    for r in reponses:
                        with st.container(key=f"qa-{r['id']}"):
                            st.markdown(etiquette_section(r.get("type") or "Question"), unsafe_allow_html=True)
                            st.markdown(f"**{r['question']}**")
                            st.write(r["texte_reponse"])

                            st.markdown(barre_score(r["score"], r["niveau_reponse"]), unsafe_allow_html=True)

                            col_f, col_a = st.columns(2)
                            with col_f:
                                st.markdown(etiquette_section("Points forts"), unsafe_allow_html=True)
                                st.markdown(liste_chips(r["points_forts"], tone="success"), unsafe_allow_html=True)
                            with col_a:
                                st.markdown(etiquette_section("Axes d'amelioration"), unsafe_allow_html=True)
                                st.markdown(liste_chips(r["axes_amelioration"], tone="warning"), unsafe_allow_html=True)

                            if r.get("feedback"):
                                st.markdown(etiquette_section("Feedback"), unsafe_allow_html=True)
                                st.caption(r["feedback"])


def vue_recruteur():
    if "ecran" not in st.session_state:
        st.session_state["ecran"] = "accueil"

    barre_navigation()

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
