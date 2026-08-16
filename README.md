# Organizador de PDFs

Software web para gerenciar e organizar arquivos PDF. Você envia listas de
presença em PDF, define **assuntos** com **palavras-chave** e o sistema identifica
automaticamente quais páginas pertencem a cada assunto. Depois você confirma a
seleção e **extrai as páginas relacionadas** em arquivos PDF separados.

## Funcionalidades

- Upload de múltiplos PDFs (máx. 50 MB cada)
- Extração automática do texto de cada página (PDFs digitais)
- Assuntos com palavras-chave (sem sensibilidade a maiúsculas/acentos)
- Correspondência página × assunto com pontuação de confiança
- Revisão manual da seleção página por página
- Extração das páginas confirmadas em um PDF por assunto + ZIP com todos
- Contas de usuário com autenticação JWT (arquivos isolados por usuário)

## Como funciona a correspondência

1. Cada página tem seu texto extraído (biblioteca PyMuPDF).
2. O texto é normalizado: minúsculas, sem acentos e espaços colapsados.
3. Para cada assunto, cada palavra-chave é procurada no texto da página.
4. A **pontuação** da página = soma das ocorrências (peso = nº de palavras da
   palavra-chave). Se todas as palavras-chave do assunto aparecerem, ganha um
   bônus. Palavras-chave compostas, ex. `prova de português`, funcionam.
5. A página com melhor pontuação é sugerida automaticamente; o usuário revisa e
   confirma antes de extrair.

## Executar localmente (Windows)

Requisitos: Python 3.12+ instalado.

```powershell
cd pdf-organizer
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env   # ajuste SECRET_KEY
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Abra `http://127.0.0.1:8000` no navegador.

Para gerar um segredo seguro:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Executar com Docker

```bash
cp .env.example .env
# edite o SECRET_KEY no .env
docker compose up -d --build
```

Acesse `http://localhost:8000`. Os dados ficam persistidos na pasta `data/`.

## Publicar em um servidor (VPS)

### 1. Instalar Docker na VPS

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # reconecte após isso
```

### 2. Enviar o projeto e subir

```bash
# na sua máquina
scp -r pdf-organizer usuario@SEU_SERVIDOR:/srv/pdf-organizer

# na VPS
cd /srv/pdf-organizer
cp .env.example .env
nano .env                     # defina um SECRET_KEY forte
docker compose up -d --build
```

### 3. Nginx como proxy reverso + HTTPS

Instale o Nginx e o certbot:

```bash
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx
```

Crie `/etc/nginx/sites-available/pdf-organizer`:

```nginx
server {
    server_name pdf.seudominio.com;

    client_max_body_size 60M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Ative e emita o certificado:

```bash
sudo ln -s /etc/nginx/sites-available/pdf-organizer /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d pdf.seudominio.com
```

### 4. Atualizar depois

```bash
cd /srv/pdf-organizer
git pull   # se usar git, ou re-envie os arquivos
docker compose up -d --build
```

## Estrutura do projeto

```
app/
  main.py             # app FastAPI
  config.py           # configurações via .env
  database.py         # SQLAlchemy (SQLite)
  models.py           # User, Subject, Keyword, Document, PageMatch
  schemas.py          # validação Pydantic
  auth.py             # senha (bcrypt) + JWT
  pdf_service.py      # extração de texto, pontuação, extração de páginas
  routers/
    auth.py           # /auth/register, /auth/login, /auth/me
    documents.py      # upload, listar, detalhe, excluir
    subjects.py       # CRUD de assuntos e palavras-chave
    extract.py        # analyze, confirm, run, download
  static/             # interface (HTML/CSS/JS)
data/                 # uploads, resultados e banco (volume Docker)
```

## API (resumo)

| Método | Rota | Descrição |
|---|---|---|
| POST | `/auth/register` | Criar conta |
| POST | `/auth/login` | Obter token |
| GET | `/auth/me` | Dados do usuário |
| POST | `/documents/upload` | Enviar PDF |
| GET | `/documents` | Listar documentos |
| DELETE | `/documents/{id}` | Excluir documento |
| POST | `/subjects` | Criar assunto com palavras-chave |
| PUT | `/subjects/{id}` | Atualizar assunto |
| DELETE | `/subjects/{id}` | Excluir assunto |
| POST | `/extract/analyze/{id}` | Analisar páginas do documento |
| POST | `/extract/confirm/{id}` | Salvar seleção manual |
| POST | `/extract/run/{id}` | Gerar PDFs por assunto + ZIP |
| GET | `/extract/download/{arquivo}` | Baixar arquivo gerado |

A documentação interativa fica em `/docs`.
