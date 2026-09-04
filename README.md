# ZEvent Website

Le projet contient deux applications independantes :

- `backend/` : API FastAPI qui met en cache l'API publique ZEvent.
- `frontend/` : dashboard Nuxt 3.

## Developpement local

Dans un premier terminal :

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Dans un second terminal :

```bash
cd frontend
npm install
npm run dev
```
