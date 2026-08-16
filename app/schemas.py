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


# ---------------------------------------------------------------- documents
class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nome_original: str
    num_paginas: int
    criado_em: datetime


# ---------------------------------------------------------------- extraction
class PaginaInfo(BaseModel):
    num_pagina: int
    data_sessao: Optional[str] = None
    hora_inicio: Optional[str] = None
    confirmada: bool = True


class PessoaResult(BaseModel):
    person_id: int
    nome: str
    paginas: List[PaginaInfo]


class AnalyzeResult(BaseModel):
    document_id: int
    pessoas: List[PessoaResult]


class ConfirmItem(BaseModel):
    person_id: int
    num_pagina: int
    confirmada: bool


class ConfirmRequest(BaseModel):
    items: List[ConfirmItem]


class ExtractResult(BaseModel):
    arquivos: List[str]
    zip_url: str
