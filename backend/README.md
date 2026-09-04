# Backend ZEvent

API FastAPI qui met en cache les donnees publiques de ZEvent et les expose au frontend.

## Demarrer localement

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

La documentation interactive est disponible sur `http://localhost:8000/docs`.

## Configuration

Copiez `.env.example` dans `.env`, puis adaptez les valeurs necessaires. Les variables sont egalement lues depuis l'environnement.

- `ZEVENT_UPSTREAM`: URL de l'API source.
- `ZEVENT_POLL_INTERVAL`: frequence de mise a jour du cache, en secondes.
- `CORS_ORIGINS`: origines frontend autorisees, separees par des virgules.

## Endpoints

- `GET /health`: etat du service.
- `GET /api/raw`: reponse ZEvent complete.
- `GET /api/summary`: donnees globales du dashboard.
- `GET /api/streamers`: liste filtrable avec `q`, `online` et `sort`.
- `GET /events`: flux SSE des mises a jour.
