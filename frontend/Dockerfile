# Frontend container — builds the React/Vite bundle, serves it from nginx, and
# reverse-proxies /api + /ws to the backend. Build context is ./frontend (this
# directory owns its own image).

# --- Stage 1: build the SPA ---
FROM node:22-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . ./
RUN npm run build

# --- Stage 2: serve + proxy ---
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
