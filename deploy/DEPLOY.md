# Deploy — Cloud Run + Cloud SQL (PostGIS)

Arquitetura: **1 container** (FastAPI serve a API `/api/*` **e** o frontend buildado) no
**Cloud Run**, falando com **Cloud SQL (Postgres 16 + PostGIS)** via socket `/cloudsql/...`.

## Pré-requisitos
- `gcloud` autenticado (`gcloud auth login`) e um projeto GCP com billing ativo.
- Docker local no ar com o Postgres de origem (`terraiq-postgis`) carregado — é a fonte do dump.

## Um comando
```bash
PROJECT=<seu-projeto> REGION=southamerica-east1 \
DBPASS='<senha-forte>' JWT_SECRET='<segredo-aleatorio>' \
bash deploy/deploy.sh
```
O script (idempotente):
1. habilita as APIs (run, sqladmin, cloudbuild, artifactregistry);
2. cria a instância Cloud SQL (Postgres 16) + usuário + banco `terraiq`;
3. **carrega os dados** (`deploy/load_data.sh`): `pg_dump` local → GCS → `gcloud sql import`, com `CREATE EXTENSION postgis` antes;
4. faz `gcloud run deploy --source .` (build pelo Dockerfile) com `--add-cloudsql-instances` e `DATABASE_URL` apontando pro socket;
5. imprime a URL pública e o `/api/health`.

## Variáveis (defaults)
| var | default | nota |
|-----|---------|------|
| `REGION` | `southamerica-east1` | São Paulo (mais perto da PB) |
| `INSTANCE` | `incorpodata-pg` | nome da instância Cloud SQL |
| `DB` / `DBUSER` | `terraiq` | mantém igual ao local (dump casa) |
| `TIER` | `db-custom-1-3840` | 1 vCPU/3.75GB. Para baratear: `db-f1-micro` (~US$8–10/mês) |
| `SERVICE` | `incorpodata` | nome do serviço Cloud Run |

## Custo (ordem de grandeza)
- **Cloud SQL** é o custo fixo: `db-f1-micro` ~US$8–10/mês; `db-custom-1-3840` ~US$50/mês. Storage 10GB ~US$1,7/mês.
- **Cloud Run**: escala a zero — só paga por request; em demo, ~US$0.
- **Artifact Registry/GCS**: centavos.
> Para uma demo barata, use `TIER=db-f1-micro`. Para desligar e parar de cobrar: `gcloud sql instances delete incorpodata-pg`.

## Pós-deploy
- A UI de login ainda não existe; para o Landbank, gere um token de dev **no banco do Cloud SQL** (rode `dev_token` apontando `DATABASE_URL` pro Cloud SQL via proxy) e use `localStorage.setItem('incorpodata_token', '<TOKEN>')`.
- Fechar `--allow-unauthenticated` ou pôr trás de IAP quando sair da fase de demo.
- Trocar `JWT_SECRET` por um segredo do Secret Manager (`--set-secrets`).

## Atualizar (re-deploy de código)
```bash
PROJECT=<seu-projeto> DBPASS=<...> JWT_SECRET=<...> bash deploy/deploy.sh
# Cloud SQL e dados já existem → ele só rebuilda e redeploya o Cloud Run.
```
> Para re-deploy só de código sem recarregar dados, rode o `gcloud run deploy --source .` do final do script direto.
