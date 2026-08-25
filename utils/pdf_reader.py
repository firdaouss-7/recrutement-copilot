# utils/pdf_reader.py
import pdfplumber


def extraire_texte_pdf(chemin_pdf: str) -> str:
    """
    Extrait le texte brut d'un CV au format PDF.

    Args:
        chemin_pdf: chemin vers le fichier PDF du CV.

    Returns:
        str: le texte complet du PDF, page par page, séparé par des sauts de ligne.

    Raises:
        FileNotFoundError: si le fichier n'existe pas.
        ValueError: si aucun texte n'a pu être extrait (ex: PDF scanné en image,
            sans couche texte — nécessiterait de l'OCR, hors périmètre ici).
    """
    texte_complet = []

    with pdfplumber.open(chemin_pdf) as pdf:
        for i, page in enumerate(pdf.pages):
            texte_page = page.extract_text()
            if texte_page:
                texte_complet.append(texte_page)

    texte_final = "\n".join(texte_complet).strip()

    if not texte_final:
        raise ValueError(
            f"Aucun texte extrait de '{chemin_pdf}'. "
            "Le PDF est peut-être scanné (image) sans couche texte — "
            "l'OCR n'est pas géré par cette fonction."
        )

    return texte_final