# ── Stage 1: Build React + Tailwind ──────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Install deps first (better layer caching)
COPY package.json package-lock.json* ./
RUN npm install

# Copy config files Tailwind needs before build
COPY tailwind.config.js postcss.config.js vite.config.js ./
COPY index.html ./
COPY src/ ./src/

# VITE_API_URL is empty — nginx proxies /api and /health to backend
RUN VITE_API_URL="" npm run build

# ── Stage 2: Serve with nginx ──────────────────────────────────────────────────
FROM nginx:alpine AS runtime

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
