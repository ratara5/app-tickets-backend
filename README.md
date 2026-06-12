# TK MGM API BACKEND
```bash
export ROOT_PATH=/path/to/your/python/projects/api-tickets-backend
$ROOT_PATH/bootstrap.sh \
    --project-root $ROOT_PATH/app-tickets-backend \
    --compose-file docker-compose.yml \
    --init-file init.sql


uvicorn app.main:app --reload
```

## Implementing open spec
Open spec is a npm package + repo in order to add agentic layer  
see https://github.com/LIDR-academy/lidr-specboot/tree/main  
Next, a summmary of lidr-specboot/README.md (and expand the instructions for items applicable to this project):  

### 1. Install and initialize openspec   
If use nvm:
```bash
install nvm --lts
nvm alias default lts/*
node --version # min 24.16.0
npm install -g @fission-ai/openspec@latest
openspec init # IN OTHER TERMINAL!
```
...

### 2. Import into your project 
... and commit: `chore: add agentic layer config (OpenSpec/specboot) (wip)`

### 3. Customize `/docs` for your project (Mandatory)  
** Generate `api-spec.json` **  

** option a **

```bash
docker compose up -f ~/Documents/GoogleCloudProjects/docker-compose.yml postgres-gci
uvicorn app.main:app --reload
curl http://localhost:8000/openapi.json -o docs/api-spec.json
```  
...

** option b **  
```bash
pip install pyyaml
python3.12 -m scripts.export_openapi
```

`scripts/export_openapi` must exist





