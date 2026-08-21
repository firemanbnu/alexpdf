# Organizador de PDFs

Software web para gerenciar e organizar arquivos PDF. Você envia **listas de
presença** em que o nome de cada pessoa aparece **à direita do campo APOC** e o
sistema separa, para cada pessoa, as páginas em que ela assinou — na ordem de
**data e horário** das sessões.

## Funcionalidades

- Upload de múltiplos PDFs (máx. 50 MB cada)
- Detecção automática de assinaturas **APOC** (nome à direita do campo)
- Páginas com o campo APOC em **branco não são contabilizadas**
- Cada pessoa recebe um PDF com as páginas em que assinou, ordenadas por
  **data e hora de início** da sessão
- Revisão manual: desmarque páginas que não deseja incluir
- Extração em PDF por pessoa + ZIP com todos
- Contas de usuário com autenticação JWT (arquivos isolados por usuário)

## Como funciona a detecção

1. Cada página é lida com a biblioteca PyMuPDF (texto extraível).
2. Palavras `APOC` na tabela de participantes (campo à esquerda) são tratadas
   como campos de assinatura; marcadores de situação (`P`, `A`, `EO`, `OC`) e
   códigos de função (`INSTR. 1`, `INSTR. 2`) são descartados.
3. O nome é o texto escrito à direita do APOC **na mesma linha**. Se o campo
   estiver em branco, a página é ignorada.
4. A **data e o horário** da sessão vêm do cabeçalho da página de conteúdo
   anterior (campos `Data:` e `Início:`).
5. As páginas de cada pessoa são agrupadas e ordenadas por `(data, início)`,
   mesmo que no PDF original as sessões não estejam em ordem cronológica.

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
  models.py           # User, Person, Document, PageMatch
  schemas.py          # validação Pydantic
  auth.py             # senha (bcrypt) + JWT
  pdf_service.py      # análise APOC, extração de páginas, ZIP
  routers/
    auth.py           # /auth/register, /auth/login, /auth/me
    documents.py      # upload, listar, excluir
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
| POST | `/extract/analyze/{id}` | Detectar assinaturas APOC e agrupar por pessoa |
| POST | `/extract/confirm/{id}` | Salvar seleção manual |
| POST | `/extract/run/{id}` | Gerar PDF por pessoa + ZIP |
| GET | `/extract/download/{arquivo}` | Baixar arquivo gerado |

A documentação interativa fica em `/docs`.
