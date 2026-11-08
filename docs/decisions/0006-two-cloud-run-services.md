# 0006 Separate API and frontend Cloud Run services
Status: accepted (README_DEPLOY_GCP.md, backend/Dockerfile, frontend/Dockerfile, frontend/nginx.conf). API container and an Nginx container serving the React build; the backend URL is baked in at build time via REACT_APP_BACKEND_URL. Region choice is open (K11).
