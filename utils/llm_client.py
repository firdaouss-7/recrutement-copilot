# utils/llm_client.py
"""
Wrapper centralise des appels a l'API Gemini.

Toutes les interactions avec le LLM (agents 1 a 4) passent par ce module :
- appeler_gemini()      : reponse texte libre
- appeler_gemini_json() : reponse JSON stricte, avec retry automatique
"""
import json
import logging
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

# Charge les variables d'environnement depuis .env
load_dotenv()

logger = logging.getLogger(__name__)


class GeminiAppelError(Exception):
    """Levée quand l'appel Gemini échoue ou renvoie une réponse inexploitable."""

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise ValueError(
        "GEMINI_API_KEY introuvable. Vérifie que le fichier .env existe "
        "à la racine du projet et contient la ligne GEMINI_API_KEY=ta_cle"
    )

# Client Gemini réutilisable par tous les agents
client = genai.Client(api_key=API_KEY)


def appeler_gemini(
    prompt: str,
    model: str = "gemini-3.5-flash-lite",
    thinking_level: str = "low",
    temperature: float | None = None,
    response_schema: dict | None = None,
):
    """
    Fonction générique d'appel à l'API Gemini, réutilisée par les 4 agents.

    Args:
        prompt: le texte complet envoyé au modèle (règles + données).
        model: identifiant exact du modèle Gemini (varie selon l'agent).
        thinking_level: "minimal", "low", "medium" ou "high".
        temperature: uniquement pris en compte sur les modèles qui l'exposent
            (ex: gemini-3-flash-preview). Ignoré sur Flash Lite / 3.6 Flash.
        response_schema: schéma JSON pour forcer une sortie structurée.

    Returns:
        Le texte brut de la réponse (JSON si un schema est fourni).
    """
    config_dict = {
        "thinking_config": {"thinking_level": thinking_level},
    }

    if temperature is not None:
        config_dict["temperature"] = temperature

    if response_schema:
        config_dict["response_mime_type"] = "application/json"
        config_dict["response_schema"] = response_schema

    config = types.GenerateContentConfig(**config_dict)

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=config,
    )

    return response.text


@retry(
    # 3 tentatives : couvre les erreurs réseau/429 transitoires ET les cas
    # où le JSON renvoyé est tronqué/invalide (relancer l'appel suffit en
    # général, la sortie structurée n'étant pas toujours identique à 100%).
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((GeminiAppelError, json.JSONDecodeError)),
    reraise=True,
)
def appeler_gemini_json(
    prompt: str,
    model: str = "gemini-3.5-flash-lite",
    thinking_level: str = "low",
    temperature: float | None = None,
    response_schema: dict | None = None,
    max_output_tokens: int = 4096,
) -> dict:
    """
    Version de appeler_gemini() dédiée aux sorties structurées (JSON) :
    - force response_mime_type=application/json (le caller n'a plus à s'en
      soucier),
    - vérifie que la réponse n'est pas vide (blocage sécurité, coupure...),
    - parse le JSON et le retourne déjà sous forme de dict,
    - retry automatique (réseau, 429, JSON tronqué) via tenacity.

    C'est le point d'entrée à utiliser dans les 4 agents à la place de
    appeler_gemini() + json.loads() manuel.

    Raises:
        GeminiAppelError: si la réponse est vide/bloquée après les tentatives.
        json.JSONDecodeError: si le JSON reste invalide après les tentatives.
    """
    config_dict = {
        "thinking_config": {"thinking_level": thinking_level},
        "response_mime_type": "application/json",
        "max_output_tokens": max_output_tokens,
    }
    if temperature is not None:
        config_dict["temperature"] = temperature
    if response_schema:
        config_dict["response_schema"] = response_schema

    config = types.GenerateContentConfig(**config_dict)

    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=config,
        )
    except Exception as exc:
        logger.warning("Appel Gemini échoué (model=%s) : %s", model, exc)
        raise GeminiAppelError(f"Erreur réseau/API Gemini : {exc}") from exc

    if not response.text:
        finish_reason = None
        if response.candidates:
            finish_reason = response.candidates[0].finish_reason
        raise GeminiAppelError(
            f"Réponse Gemini vide (model={model}, finish_reason={finish_reason}). "
            "Le contenu a peut-être été bloqué par un filtre de sécurité, "
            "ou la génération a atteint max_output_tokens avant la fin du JSON."
        )

    try:
        return json.loads(response.text)
    except json.JSONDecodeError:
        logger.warning(
            "JSON invalide reçu de Gemini (model=%s), tentative de retry. "
            "Début de la réponse : %.200s",
            model,
            response.text,
        )
        raise