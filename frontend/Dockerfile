# ── Build stage ───────────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /frontend

# Install dependencies
COPY package.json package-lock.json* ./
RUN npm ci

# Copy source and build
# The vite.config.ts reads ../.env for the dev-server proxy only;
# the static build emits relative /api/* paths that nginx will proxy.
COPY . .
RUN npm run build

# ── Serve stage ───────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS runner

# Nginx config with SPA routing and API proxy to backend
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets
COPY --from=builder /frontend/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
