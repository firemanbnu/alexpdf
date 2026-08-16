import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..auth import obter_usuario_atual
from ..config import settings
from ..database import get_db
from ..models import Document, PageMatch, Subject, User
from ..pdf_service import (
    analisar_paginas,
    cleanup_resultados,
    criar_zip,
    extrair_paginas,
    slugify,
)
from ..schemas import AnalyzeResult, ConfirmRequest, ExtractResult, PageAnalysis, PageMatchOut

router = APIRouter(prefix="/extract", tags=["extract"])


def _get_doc(doc_id: int, user: User, db: Session) -> Document:
    doc = db.get(Document, doc_id)
    if not doc or doc.user_id != user.id:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    return doc


def _get_subjects(user: User, db: Session) -> list[Subject]:
    return db.query(Subject).filter(Subject.user_id == user.id).all()


def _build_analyze_result(doc: Document, db: Session) -> AnalyzeResult:
    rows = db.query(PageMatch).filter(PageMatch.document_id == doc.id).all()
    paginas = []
    for num in range(1, doc.num_paginas + 1):
        page_rows = [r for r in rows if r.num_pagina == num]
        matches = [
            PageMatchOut(
                subject_id=r.subject_id,
                num_pagina=r.num_pagina,
                score=r.score,
                confirmada=r.confirmada,
            )
            for r in sorted(page_rows, key=lambda r: r.score, reverse=True)
        ]
        texto = page_rows[0].texto_exemplo if page_rows else ""
        paginas.append(
            PageAnalysis(
                num_pagina=num,
                texto_preview=texto,
                matches=matches,
                melhor_subject_id=matches[0].subject_id if matches else None,
            )
        )
    return AnalyzeResult(document_id=doc.id, paginas=paginas)


@router.post("/analyze/{doc_id}", response_model=AnalyzeResult)
def analyze(
    doc_id: int, user: User = Depends(obter_usuario_atual), db: Session = Depends(get_db)
):
    doc = _get_doc(doc_id, user, db)
    subjects = _get_subjects(user, db)
    if not subjects:
        raise HTTPException(
            status_code=400,
            detail="Crie ao menos um assunto com palavras-chave antes de analisar",
        )

    analise = analisar_paginas(doc, subjects)

    db.query(PageMatch).filter(PageMatch.document_id == doc.id).delete()
    db.flush()

    for item in analise:
        for m in item["matches"]:
            is_best = item["melhor_subject_id"] == m["subject_id"]
            db.add(
                PageMatch(
                    document_id=doc.id,
                    subject_id=m["subject_id"],
                    num_pagina=m["num_pagina"],
                    score=m["score"],
                    confirmada=is_best,
                    texto_exemplo=item["texto_preview"][:300],
                )
            )
    db.commit()

    return _build_analyze_result(doc, db)


@router.post("/confirm/{doc_id}", response_model=AnalyzeResult)
def confirm(
    doc_id: int,
    dados: ConfirmRequest,
    user: User = Depends(obter_usuario_atual),
    db: Session = Depends(get_db),
):
    doc = _get_doc(doc_id, user, db)
    subj_ids = {s.id for s in _get_subjects(user, db)}

    desejadas = {(i.subject_id, i.num_pagina) for i in dados.items if i.confirmada}
    for item in dados.items:
        if item.subject_id not in subj_ids:
            raise HTTPException(status_code=400, detail="Assunto inválido")

    rows = db.query(PageMatch).filter(PageMatch.document_id == doc.id).all()
    rows_por_chave = {(r.subject_id, r.num_pagina): r for r in rows}

    for chave, row in rows_por_chave.items():
        row.confirmada = chave in desejadas

    for subject_id, num_pagina in desejadas:
        if (subject_id, num_pagina) not in rows_por_chave:
            db.add(
                PageMatch(
                    document_id=doc.id,
                    subject_id=subject_id,
                    num_pagina=num_pagina,
                    score=0.0,
                    confirmada=True,
                )
            )
    db.commit()

    return _build_analyze_result(doc, db)


@router.post("/run/{doc_id}", response_model=ExtractResult)
def run(
    doc_id: int, user: User = Depends(obter_usuario_atual), db: Session = Depends(get_db)
):
    doc = _get_doc(doc_id, user, db)
    rows = (
        db.query(PageMatch)
        .filter(PageMatch.document_id == doc.id, PageMatch.confirmada.is_(True))
        .all()
    )
    if not rows:
        raise HTTPException(
            status_code=400, detail="Nenhuma página confirmada para extrair"
        )

    cleanup_resultados(doc)

    por_assunto: dict[int, list[int]] = {}
    for r in rows:
        por_assunto.setdefault(r.subject_id, []).append(r.num_pagina)

    arquivos: list[Path] = []
    for subject_id, paginas in por_assunto.items():
        subj = db.get(Subject, subject_id)
        if not subj or subj.user_id != user.id:
            continue
        destino = settings.results_dir / f"doc{doc.id}_{slugify(subj.nome)}.pdf"
        extrair_paginas(Path(doc.caminho_arquivo), paginas, destino)
        arquivos.append(destino)

    if not arquivos:
        raise HTTPException(status_code=400, detail="Nenhum assunto válido confirmado")

    zip_path = criar_zip(arquivos, settings.results_dir / f"doc{doc.id}_todas.zip")
    arquivos.append(zip_path)
    return ExtractResult(
        arquivos=[f.name for f in arquivos],
        zip_url=f"/extract/download/{zip_path.name}",
    )


@router.get("/download/{filename}")
def download(
    filename: str, user: User = Depends(obter_usuario_atual), db: Session = Depends(get_db)
):
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido")
    match = re.match(r"^doc(\d+)_", filename)
    if not match:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    doc = _get_doc(int(match.group(1)), user, db)
    path = settings.results_dir / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    return FileResponse(path, filename=filename)
