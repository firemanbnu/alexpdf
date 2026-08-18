import re
import unicodedata
import zipfile
from pathlib import Path

import fitz

from .config import settings
from .models import Document

# ------------------------------------------------------------------ normalização
_STRIP_RE = re.compile(r"[\s\-—_.,;:()\[\]/|]+")

DATA_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
HORA_RE = re.compile(r"^\d{1,2}:\d{2}$")

# Assinaturas APOC ficam na parte inferior da página (campos fixos do formulário).
_REGIAO_ASSINATURA = 180.0


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


# ------------------------------------------------------------------ análise por APOC
def _agrupar_linhas(words: list, tol: float = 4.0) -> list[dict]:
    """Agrupa palavras que compartilham a mesma linha visual (por y central)."""
    linhas: list[dict] = []
    for w in sorted(words, key=lambda w: (w[1], w[0])):
        yc = (w[1] + w[3]) / 2.0
        for linha in linhas:
            if abs(linha["yc"] - yc) <= tol:
                linha["words"].append(w)
                break
        else:
            linhas.append({"yc": yc, "words": [w]})
    for linha in linhas:
        linha["words"].sort(key=lambda w: w[0])
    return linhas


def extrair_data_hora(words: list, limiar_y: float = 200.0) -> tuple[str | None, str | None]:
    """Data e hora de início a partir do cabeçalho da página de conteúdo."""
    cabecalho = [w for w in words if w[1] < limiar_y]
    datas = [w[4] for w in cabecalho if DATA_RE.match(w[4])]
    horas = sorted([w for w in cabecalho if HORA_RE.match(w[4])], key=lambda w: w[0])
    data = datas[0] if datas else None
    inicio = horas[0][4] if horas else None
    return data, inicio


def analisar_apoc(pdf_path: Path) -> list[dict]:
    """Varre o PDF e retorna, por página, as assinaturas APOC com o nome
    escrito à esquerda e a data/hora de início da sessão (da página de
    conteúdo mais próxima anterior). Páginas sem nome não geram assinatura."""
    doc = fitz.open(pdf_path)
    try:
        paginas_info = []
        for num, page in enumerate(doc, start=1):
            words = page.get_text("words")
            data, inicio = extrair_data_hora(words)
            limiar_y = page.rect.height - _REGIAO_ASSINATURA

            assinaturas: list[str] = []
            for linha in _agrupar_linhas(words):
                apocs = [
                    w
                    for w in linha["words"]
                    if w[4].strip().upper() == "APOC" and w[1] >= limiar_y
                ]
                for apoc in apocs:
                    nome_parts = [w[4] for w in linha["words"] if w[2] <= apoc[0]]
                    nome = " ".join(nome_parts).strip(" ;,.-")
                    if nome:
                        assinaturas.append(nome)
            paginas_info.append(
                {"num": num, "data": data, "inicio": inicio, "assinaturas": assinaturas}
            )

        # A página de participantes vem logo após a de conteúdo; usa-se a
        # data/hora mais recente encontrada para trás.
        ultima = (None, None)
        for p in paginas_info:
            if p["data"] and p["inicio"]:
                ultima = (p["data"], p["inicio"])
            elif p["data"]:
                ultima = (p["data"], ultima[1])
            p["sessao_data"] = ultima[0]
            p["sessao_inicio"] = ultima[1]
        return paginas_info
    finally:
        doc.close()


def _separar_nomes(nome: str) -> list[str]:
    return [n.strip() for n in nome.split(";") if n.strip()]


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


def criar_pdf_compilado(
    pdf_path: Path, todas_paginas: list[int], destino: Path
) -> Path:
    """Cria um único PDF com todas as páginas na ordem informada."""
    paginas_ordenadas = [int(p) for p in todas_paginas if int(p) >= 1]
    with fitz.open(pdf_path) as doc:
        total = doc.page_count
        paginas_validas = [p - 1 for p in paginas_ordenadas if p <= total]
        if not paginas_validas:
            raise ValueError("Nenhuma válida para compilar")
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
