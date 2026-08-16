import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..auth import obter_usuario_atual
from ..config import settings
from ..database import get_db
from ..models import Document, PageMatch, User
from ..pdf_service import extrair_texto_paginas, validar_pdf
from ..schemas import DocumentDetail, DocumentOut

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload(
    file: UploadFile = File(...),
    user: User = Depends(obter_usuario_atual),
    db: Session = Depends(get_db),
):
    nome_limpo = Path(file.filename or "sem_nome.pdf").name
    if not nome_limpo.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Somente arquivos PDF são aceitos")

    conteudo = await file.read()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(conteudo) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo excede o limite de {settings.max_upload_mb} MB",
        )

    user_dir = settings.uploads_dir / str(user.id)
    user_dir.mkdir(parents=True, exist_ok=True)
    armazenado = user_dir / f"{uuid.uuid4().hex}_{nome_limpo}"
    armazenado.write_bytes(conteudo)

    if not validar_pdf(armazenado):
        armazenado.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Arquivo inválido ou corrompido")

    paginas = len(extrair_texto_paginas(armazenado))
    doc = Document(
        user_id=user.id,
        nome_original=nome_limpo,
        caminho_arquivo=str(armazenado),
        num_paginas=paginas,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


@router.get("", response_model=list[DocumentOut])
def listar(user: User = Depends(obter_usuario_atual), db: Session = Depends(get_db)):
    return (
        db.query(Document)
        .filter(Document.user_id == user.id)
        .order_by(Document.criado_em.desc())
        .all()
    )


@router.get("/{doc_id}", response_model=DocumentDetail)
def detalhe(
    doc_id: int,
    user: User = Depends(obter_usuario_atual),
    db: Session = Depends(get_db),
):
    doc = db.get(Document, doc_id)
    if not doc or doc.user_id != user.id:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    matches = db.query(PageMatch).filter(PageMatch.document_id == doc.id).all()
    return DocumentDetail(
        id=doc.id,
        nome_original=doc.nome_original,
        num_paginas=doc.num_paginas,
        criado_em=doc.criado_em,
        paginas_texto=extrair_texto_paginas(Path(doc.caminho_arquivo)),
        matches=matches,
    )


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir(
    doc_id: int,
    user: User = Depends(obter_usuario_atual),
    db: Session = Depends(get_db),
):
    doc = db.get(Document, doc_id)
    if not doc or doc.user_id != user.id:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    path = Path(doc.caminho_arquivo)
    path.unlink(missing_ok=True)
    db.delete(doc)
    db.commit()
