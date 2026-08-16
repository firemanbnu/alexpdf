from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import obter_usuario_atual
from ..database import get_db
from ..models import Keyword, PageMatch, Subject, User
from ..schemas import SubjectCreate, SubjectOut, SubjectUpdate

router = APIRouter(prefix="/subjects", tags=["subjects"])


def _subject_para_out(subj: Subject) -> SubjectOut:
    return SubjectOut(
        id=subj.id,
        nome=subj.nome,
        keywords=[{"id": k.id, "palavra": k.palavra} for k in subj.keywords],
    )


@router.post("", response_model=SubjectOut, status_code=status.HTTP_201_CREATED)
def criar(
    dados: SubjectCreate,
    user: User = Depends(obter_usuario_atual),
    db: Session = Depends(get_db),
):
    subj = Subject(user_id=user.id, nome=dados.nome)
    db.add(subj)
    db.flush()
    for kw in dados.keywords:
        palavra = kw.strip()
        if palavra:
            db.add(Keyword(subject_id=subj.id, palavra=palavra))
    db.commit()
    db.refresh(subj)
    return _subject_para_out(subj)


@router.get("", response_model=list[SubjectOut])
def listar(user: User = Depends(obter_usuario_atual), db: Session = Depends(get_db)):
    subjects = (
        db.query(Subject).filter(Subject.user_id == user.id).order_by(Subject.nome).all()
    )
    return [_subject_para_out(s) for s in subjects]


@router.put("/{subj_id}", response_model=SubjectOut)
def atualizar(
    subj_id: int,
    dados: SubjectUpdate,
    user: User = Depends(obter_usuario_atual),
    db: Session = Depends(get_db),
):
    subj = db.get(Subject, subj_id)
    if not subj or subj.user_id != user.id:
        raise HTTPException(status_code=404, detail="Assunto não encontrado")
    if dados.nome is not None:
        subj.nome = dados.nome
    if dados.keywords is not None:
        for kw in subj.keywords:
            db.delete(kw)
        db.flush()
        for kw in dados.keywords:
            palavra = kw.strip()
            if palavra:
                db.add(Keyword(subject_id=subj.id, palavra=palavra))
    db.commit()
    db.refresh(subj)
    return _subject_para_out(subj)


@router.delete("/{subj_id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir(
    subj_id: int,
    user: User = Depends(obter_usuario_atual),
    db: Session = Depends(get_db),
):
    subj = db.get(Subject, subj_id)
    if not subj or subj.user_id != user.id:
        raise HTTPException(status_code=404, detail="Assunto não encontrado")
    db.query(PageMatch).filter(PageMatch.subject_id == subj.id).delete()
    db.delete(subj)
    db.commit()
