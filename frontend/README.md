# Frontend ZEvent

Dashboard Nuxt 3 consommant l'API FastAPI du dossier `../backend`.

## Demarrer localement

```bash
npm install
npm run dev
```

L'application est servie sur `http://localhost:3000` et attend l'API sur `http://localhost:8000` par defaut.

## Configuration

Copiez `.env.example` vers `.env` pour definir `NUXT_PUBLIC_API_BASE` lorsque l'API est hebergee sur une autre adresse.

## Production

```bash
npm run build
npm run preview
```
