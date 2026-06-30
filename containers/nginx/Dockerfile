# Public gateway nginx — single front door that routes /api + /ws to the backend
# (Daphne) and everything else to the frontend static server. Build context is
# containers/nginx (config only; no app build here).
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
