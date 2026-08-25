# test_llm_client.py
from utils.llm_client import appeler_gemini
import json

# Schéma minimal, juste pour valider que l'appel API fonctionne de bout en bout
schema_test = {
    "type": "object",
    "properties": {
        "nom": {"type": "string"},
        "competences": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["nom", "competences"]
}

prompt_test = """
Voici un CV très court. Extrais le nom et les compétences en JSON.

CV : Jean Dupont, développeur Python avec 3 ans d'expérience en Django et PostgreSQL.
"""

print("Test — Appel API Gemini avec structured output...")
resultat = appeler_gemini(
    prompt=prompt_test,
    model="gemini-3.5-flash-lite",
    thinking_level="low",
    response_schema=schema_test,
)

print("\nRéponse brute reçue :")
print(resultat)

try:
    parsed = json.loads(resultat)
    print("\n✅ JSON valide, parsing réussi :")
    print(parsed)
except json.JSONDecodeError as e:
    print(f"\n❌ Erreur de parsing JSON : {e}")