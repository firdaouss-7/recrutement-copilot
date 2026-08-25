# email_utils/envoi.py
#
# Envoi du lien d'entretien au candidat par email (Gmail SMTP).
# Necessite dans .env :
#   GMAIL_ADRESSE=exemple@gmail.com
#   GMAIL_MOT_DE_PASSE_APP=xxxxxxxxxxxxxxxx   (mot de passe d'application, pas le mdp normal)
#   APP_BASE_URL=http://localhost:8501

import os
import smtplib
import logging
from email.mime.text import MIMEText

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

GMAIL_ADRESSE = os.getenv("GMAIL_ADRESSE")
GMAIL_MOT_DE_PASSE_APP = os.getenv("GMAIL_MOT_DE_PASSE_APP")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8501")


def construire_lien_entretien(token: str) -> str:
    return f"{APP_BASE_URL}/?token={token}"


def envoyer_lien_entretien(email_destinataire: str, nom_candidat: str, token: str) -> bool:
    """
    Envoie le lien d'entretien au candidat.

    Returns:
        True si l'email a ete envoye, False sinon (erreur loguee).
    """
    if not GMAIL_ADRESSE or not GMAIL_MOT_DE_PASSE_APP:
        logger.error("GMAIL_ADRESSE ou GMAIL_MOT_DE_PASSE_APP manquant dans .env")
        return False

    lien = construire_lien_entretien(token)

    corps = (
        f"Bonjour {nom_candidat},\n\n"
        "Dans le cadre de votre candidature, nous vous invitons a repondre "
        "a quelques questions d'entretien en suivant le lien ci-dessous :\n\n"
        f"{lien}\n\n"
        "Ce lien est personnel et a usage unique.\n\n"
        "Cordialement,\n"
        "L'equipe recrutement"
    )

    message = MIMEText(corps, "plain", "utf-8")
    message["Subject"] = "Votre entretien - lien pour repondre aux questions"
    message["From"] = GMAIL_ADRESSE
    message["To"] = email_destinataire

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as serveur:
            serveur.login(GMAIL_ADRESSE, GMAIL_MOT_DE_PASSE_APP)
            serveur.sendmail(GMAIL_ADRESSE, [email_destinataire], message.as_string())
        logger.info("Email envoye a %s", email_destinataire)
        return True
    except Exception:
        logger.exception("Echec envoi email a %s", email_destinataire)
        return False