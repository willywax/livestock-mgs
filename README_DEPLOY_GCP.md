                                                                                                qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq# GCP Cloud Run Deployment (Frontend + Backend + Neon)

This project deploys two Cloud Run services:
- **backend**: FastAPI API
- **frontend**: Static React build served by Nginx

## 1) Prereqs
- GCP project created
- `gcloud` authenticated: `gcloud auth login`
- Set project: `gcloud config set project elitagroup`

## 2) Build & deploy backend
From repo root:

```bash
# Build and deploy backend
cd backend

gcloud builds submit --tag gcr.io/elitagroup/shamba-backend

gcloud run deploy shamba-backend \
  --image gcr.io/elitagroup/shamba-backend \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars DATABASE_URL="YOUR_NEON_URL",CORS_ORIGINS="YOUR_FRONTEND_URL",JWT_SECRET="YOUR_JWT_SECRET"
```

## 3) Build & deploy frontend
From repo root:

```bash
cd frontend

gcloud builds submit \
  --tag gcr.io/elitagroup/srcstock \
  --build-arg REACT_APP_BACKEND_URL=YOUR_BACKEND_URL

gcloud run deploy srcstock \
  --image gcr.io/elitagroup/srcstock \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```

## 4) Notes
- Set `CORS_ORIGINS` to the full frontend URL (comma-separated for multiple).
- For Neon, use the standard postgres URL you provided. The backend normalizes it for asyncpg.
- If you need a separate staging/prod, deploy two services with different names and env vars.
