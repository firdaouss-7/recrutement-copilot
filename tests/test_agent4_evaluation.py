# tests/test_agent4_evaluation.py
#
# Test de l'Agent 4 en isolation, sur le principe du rapport (section 5.4) :
# une même question, 3 reponses candidat de qualite contrastee (faible /
# ambigue / forte), pour verifier que le score et le mapping score->niveau
# sont coherents.
#
# On reutilise une question technique deja generee par l'Agent 3 (sortie
# reelle du pipeline), pour rester coherent avec le reste du projet plutot
# que d'inventer une question isolee.
#
# Usage (depuis la racine du projet) :
#   python -m tests.test_agent4_evaluation

from agents.agent4_evaluation import evaluer_reponse_candidat

# Question technique reelle, issue de l'Agent 3 (test cv2, "avec RAG")
QUESTION = (
    "Quelle methode utilisez-vous pour conteneuriser une application "
    "Python de Machine Learning a l'aide de Docker afin de preparer sa "
    "mise en production ?"
)

REPONSES_TEST = {
    "Reponse forte": (
        "Je pars d'une image Python slim officielle, je fige les "
        "dependances dans un requirements.txt avec des versions "
        "epinglees, et je structure le Dockerfile en plusieurs stages "
        "pour separer build et runtime et reduire la taille de l'image. "
        "Le modele est charge au demarrage du conteneur, expose via une "
        "API FastAPI, et j'ajoute un healthcheck. En CI/CD (Jenkins), "
        "l'image est buildee, testee puis poussee sur un registre avant "
        "deploiement sur Kubernetes, avec un monitoring du drift via "
        "Grafana une fois en production."
    ),
    "Reponse moyenne / ambigue": (
        "Je n'ai jamais mis en place la conteneurisation moi-meme, mais "
        "j'ai travaille en collaboration etroite avec l'equipe DevOps : "
        "je leur fournissais le modele et les dependances necessaires, "
        "et eux prenaient en charge le Dockerfile et le deploiement. Je "
        "comprends les grandes etapes mais je ne les ai pas executees "
        "en autonomie."
    ),
    "Reponse faible": (
        "Je ne connais pas vraiment Docker, je ne m'en suis jamais "
        "occupe et je ne saurais pas dire comment ca fonctionne."
    ),
}


def main():
    print(f"Question testee :\n{QUESTION}\n")

    for label, reponse in REPONSES_TEST.items():
        print(f"=== {label} ===")
        resultat = evaluer_reponse_candidat(QUESTION, reponse)

        print(f"Score : {resultat['score']}")
        print(f"Niveau : {resultat['niveau_reponse']}")
        print(f"Points forts : {resultat['points_forts']}")
        print(f"Axes d'amelioration : {resultat['axes_amelioration']}")
        print(f"Feedback : {resultat['feedback']}")
        print()


if __name__ == "__main__":
    main()