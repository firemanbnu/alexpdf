from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# ---------------------------------------------------------------- auth
class UserCreate(BaseModel):
    nome: str = Field(min_length=2, max_length=120)
    email: EmailStr
    senha: str = Field(min_length=6, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: EmailStr
    senha: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nome: str
    email: str
    criado_em: datetime


# ---------------------------------------------------------------- subjects
class KeywordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    palavra: str


class SubjectCreate(BaseModel):
    nome: str = Field(min_length=1, max_length=200)
    keywords: List[str] = Field(default_factory=list)


class SubjectUpdate(BaseModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=200)
    keywords: Optional[List[str]] = None


class SubjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nome: str
    keywords: List[KeywordOut]


# ---------------------------------------------------------------- documents
class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nome_original: str
    num_paginas: int
    criado_em: datetime


class DocumentDetail(DocumentOut):
    paginas_texto: List[str] = []
    matches: List["PageMatchOut"] = []


class PageMatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    subject_id: int
    num_pagina: int
    score: float
    confirmada: bool


# ---------------------------------------------------------------- extraction
class AnalyzeResult(BaseModel):
    document_id: int
    paginas: List["PageAnalysis"]


class PageAnalysis(BaseModel):
    num_pagina: int
    texto_preview: str
    matches: List["PageMatchOut"]
    melhor_subject_id: Optional[int] = None


class ConfirmItem(BaseModel):
    subject_id: int
    num_pagina: int
    confirmada: bool


class ConfirmRequest(BaseModel):
    items: List[ConfirmItem]


class ExtractResult(BaseModel):
    arquivos: List[str]
    zip_url: str


DocumentDetail.model_rebuild()
AnalyzeResult.model_rebuild()
PageAnalysis.model_rebuild()
