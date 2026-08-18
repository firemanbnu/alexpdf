import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..auth import obter_usuario_atual
from ..config import settings
from ..database import get_db
from ..models import Document, PageMatch, Person, User
from ..pdf_service import (
    _separar_nomes,
    analisar_apoc,
    cleanup_resultados,
    criar_pdf_compilado,
    slugify,
)
from ..schemas import AnalyzeResult, ConfirmRequest, ExtractResult, PaginaInfo, PessoaResult

router = APIRouter(prefix="/extract", tags=["extract"])


def _get_doc(doc_id: int, user: User, db: Session) -> Document:
    doc = db.get(Document, doc_id)
    if not doc or doc.user_id != user.id:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    return doc


def _get_persons(user: User, db: Session) -> dict[str, Person]:
    return {
        p.nome.lower(): p
        for p in db.query(Person).filter(Person.user_id == user.id).all()
    }


def _build_result(doc: Document, db: Session) -> AnalyzeResult:
    rows = db.query(PageMatch).filter(PageMatch.document_id == doc.id).all()
    pessoas: dict[int, list[PageMatch]] = {}
    for r in rows:
        pessoas.setdefault(r.person_id, []).append(r)

    resultado: list[PessoaResult] = []
    for person_id, ms in pessoas.items():
        person = db.get(Person, person_id)
        if not person:
            continue
        paginas = [
            PaginaInfo(
                num_pagina=r.num_pagina,
                data_sessao=r.data_sessao,
                hora_inicio=r.hora_inicio,
                confirmada=r.confirmada,
            )
            for r in ms
        ]
        paginas.sort(
            key=lambda p: (
                _chave(p.data_sessao, p.hora_inicio),
                p.num_pagina,
            )
        )
        resultado.append(PessoaResult(person_id=person.id, nome=person.nome, paginas=paginas))

    resultado.sort(key=lambda r: r.nome.lower())
    return AnalyzeResult(document_id=doc.id, pessoas=resultado)


def _chave(data: str | None, hora: str | None) -> tuple[int, int, int, int, int]:
    ano = mes = dia = h = min_ = 0
    if data:
        try:
            d, m, a = (int(x) for x in data.split("/"))
            ano, mes, dia = a, m, d
        except ValueError:
            pass
    if hora:
        try:
            h, min_ = (int(x) for x in hora.split(":"))
        except ValueError:
            pass
    return (ano, mes, dia, h, min_)


@router.post("/analyze/{doc_id}", response_model=AnalyzeResult)
def analyze(
    doc_id: int, user: User = Depends(obter_usuario_atual), db: Session = Depends(get_db)
):
    doc = _get_doc(doc_id, user, db)
    infos = analisar_apoc(Path(doc.caminho_arquivo))

    db.query(PageMatch).filter(PageMatch.document_id == doc.id).delete()
    db.flush()

    persons = _get_persons(user, db)
    vistos: set[tuple[int, int]] = set()
    for info in infos:
        for nome in info["assinaturas"]:
            for parte in _separar_nomes(nome):
                chave = parte.lower()
                person = persons.get(chave)
                if person is None:
                    person = Person(user_id=user.id, nome=parte)
                    db.add(person)
                    db.flush()
                    persons[chave] = person
                if (person.id, info["num"]) in vistos:
                    continue
                vistos.add((person.id, info["num"]))
                db.add(
                    PageMatch(
                        document_id=doc.id,
                        person_id=person.id,
                        num_pagina=info["num"],
                        data_sessao=info["sessao_data"],
                        hora_inicio=info["sessao_inicio"],
                        confirmada=True,
                    )
                )
    db.commit()
    return _build_result(doc, db)


@router.post("/confirm/{doc_id}", response_model=AnalyzeResult)
def confirm(
    doc_id: int,
    dados: ConfirmRequest,
    user: User = Depends(obter_usuario_atual),
    db: Session = Depends(get_db),
):
    doc = _get_doc(doc_id, user, db)
    persons = _get_persons(user, db)
    person_ids = {p.id for p in persons.values()}
    for item in dados.items:
        if item.person_id not in person_ids:
            raise HTTPException(status_code=400, detail="Pessoa inválida")

    desejadas = {(i.person_id, i.num_pagina) for i in dados.items if i.confirmada}

    rows = db.query(PageMatch).filter(PageMatch.document_id == doc.id).all()
    rows_por_chave = {(r.person_id, r.num_pagina): r for r in rows}
    for chave, row in rows_por_chave.items():
        row.confirmada = chave in desejadas

    for person_id, num_pagina in desejadas:
        if (person_id, num_pagina) not in rows_por_chave:
            db.add(
                PageMatch(
                    document_id=doc.id,
                    person_id=person_id,
                    num_pagina=num_pagina,
                    confirmada=True,
                )
            )
    db.commit()
    return _build_result(doc, db)


@router.post("/run/{doc_id}", response_model=ExtractResult)
def run(
    doc_id: int, user: User = Depends(obter_usuario_atual), db: Session = Depends(get_db)
):
    doc = _get_doc(doc_id, user, db)
    rows = (
        db.query(PageMatch)
        .filter(PageMatch.document_id == doc.id)
        .all()
    )
    if not rows:
        raise HTTPException(
            status_code=400, detail="Nenhuma página encontrada para extrair"
        )

    cleanup_resultados(doc)

    paginas_unicas = sorted({r.num_pagina for r in rows})

    nome_arquivo = f"doc{doc.id}_compilacao_de_PTRBA_APOC.pdf"
    compilado = criar_pdf_compilado(
        Path(doc.caminho_arquivo),
        paginas_unicas,
        settings.results_dir / nome_arquivo,
    )

    return ExtractResult(
        arquivos=[compilado.name],
        zip_url="",
        compilado_url=f"/extract/download/{compilado.name}",
    )


@router.get("/download/{filename}")
def download(
    filename: str, user: User = Depends(obter_usuario_atual), db: Session = Depends(get_db)
):
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido")
    match = re.match(r"^doc(\d+)_", filename)
    if match:
        doc = _get_doc(int(match.group(1)), user, db)
    path = settings.results_dir / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    return FileResponse(path, filename=filename)
