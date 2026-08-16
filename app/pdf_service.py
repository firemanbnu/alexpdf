import re
import unicodedata
import zipfile
from pathlib import Path

import fitz

from .config import settings
from .models import Document, Subject

# ------------------------------------------------------------------ normalização
_STRIP_RE = re.compile(r"[\s\-—_.,;:()\[\]/|]+")


def normalizar(texto: str) -> str:
    """Minúsculas, sem acentos e com espaçadores múltiplos colapsados."""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.lower()
    texto = _STRIP_RE.sub(" ", texto)
    return " ".join(texto.split())


def slugify(nome: str) -> str:
    nome = normalizar(nome).replace(" ", "_")
    return re.sub(r"[^a-z0-9_]", "", nome) or "arquivo"


# ------------------------------------------------------------------ extração de texto
def extrair_texto_paginas(pdf_path: Path) -> list[str]:
    doc = fitz.open(pdf_path)
    try:
        return [page.get_text("text") for page in doc]
    finally:
        doc.close()


def validar_pdf(path: Path) -> bool:
    try:
        with fitz.open(path) as doc:
            return doc.page_count > 0
    except Exception:
        return False


# ------------------------------------------------------------------ correspondência
def _keyword_tokens(palavra: str) -> list[str]:
    return [t for t in normalizar(palavra).split() if t]


def calcular_score(texto_pagina: str, keywords: list[str]) -> float:
    texto = normalizar(texto_pagina)
    score = 0.0
    encontradas = 0
    for kw in keywords:
        tokens = _keyword_tokens(kw)
        if not tokens:
            continue
        frase = " ".join(tokens)
        ocorrencias = texto.count(frase)
        if ocorrencias > 0:
            score += float(ocorrencias) * len(tokens)
            encontradas += 1
    if keywords and encontradas == len([k for k in keywords if _keyword_tokens(k)]):
        score += 2.0
    return score


def analisar_paginas(doc: Document, subjects: list[Subject]) -> list[dict]:
    """Retorna análise por página: lista de {subject_id, score} e texto preview."""
    paginas = extrair_texto_paginas(Path(doc.caminho_arquivo))
    resultado = []
    for num, texto in enumerate(paginas, start=1):
        matches = []
        for subj in subjects:
            keywords = [k.palavra for k in subj.keywords]
            if not keywords:
                continue
            score = calcular_score(texto, keywords)
            if score >= settings.min_keyword_score:
                matches.append(
                    {"subject_id": subj.id, "num_pagina": num, "score": score}
                )
        matches.sort(key=lambda m: m["score"], reverse=True)
        preview = " ".join(texto.split())[:500]
        resultado.append(
            {
                "num_pagina": num,
                "texto_preview": preview,
                "matches": matches,
                "melhor_subject_id": matches[0]["subject_id"] if matches else None,
            }
        )
    return resultado


# ------------------------------------------------------------------ extração de PDF
def extrair_paginas(pdf_path: Path, paginas: list[int], destino: Path) -> Path:
    paginas_limpas = sorted({int(p) for p in paginas if int(p) >= 1})
    with fitz.open(pdf_path) as doc:
        total = doc.page_count
        paginas_validas = [p - 1 for p in paginas_limpas if p <= total]
        if not paginas_validas:
            raise ValueError("Nenhuma página válida para extrair")
        doc.select(paginas_validas)
        doc.save(destino, garbage=4, deflate=True)
    return destino


def criar_zip(arquivos: list[Path], destino: Path) -> Path:
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in arquivos:
            zf.write(f, arcname=f.name)
    return destino


def cleanup_resultados(doc: Document) -> None:
    """Apaga PDFs/ZIP gerados anteriormente para este documento."""
    prefix = f"doc{doc.id}_"
    for f in settings.results_dir.glob(f"{prefix}*"):
        try:
            f.unlink()
        except OSError:
            pass
