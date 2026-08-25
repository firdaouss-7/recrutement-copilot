import json
import os

dossier = "data/questions_bank"
corpus_final = []

for fichier in sorted(os.listdir(dossier)):
    if fichier.endswith(".json") and fichier != "corpus_final.json":
        chemin = os.path.join(dossier, fichier)
        with open(chemin, "r", encoding="utf-8") as f:
            questions = json.load(f)
            corpus_final.extend(questions)
            print(f"{fichier} : {len(questions)} questions")

# Vérification des doublons d'ID
ids = [q["id"] for q in corpus_final]
doublons = set([i for i in ids if ids.count(i) > 1])
if doublons:
    print("⚠️ IDs dupliqués détectés :", doublons)
else:
    print(f"\n{len(corpus_final)} questions fusionnées, aucun ID dupliqué.")

with open(os.path.join(dossier, "corpus_final.json"), "w", encoding="utf-8") as f:
    json.dump(corpus_final, f, ensure_ascii=False, indent=2)