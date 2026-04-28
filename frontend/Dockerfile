# Dockerfile multi-stage para o Admin Panel (Next.js).
# Gera imagem leve usando o modo standalone do Next.js.
#
# Uso:
#   docker compose up -d frontend

# ---- 1. Instala dependências ----
FROM node:22-alpine AS deps

WORKDIR /app

# Copia apenas os arquivos de dependências para aproveitar cache do Docker
COPY package.json package-lock.json* ./
RUN npm ci

# ---- 2. Build da aplicação ----
FROM node:22-alpine AS build

WORKDIR /app

# Copia dependências instaladas no estágio anterior
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Gera o build standalone (definido em next.config.ts)
RUN npm run build

# ---- 3. Imagem final (apenas o necessário para rodar) ----
FROM node:22-alpine AS runtime

WORKDIR /app

# Cria usuário não-root por segurança
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Copia arquivos estáticos e o servidor standalone
COPY --from=build /app/public ./public
COPY --from=build --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=build --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Inicia o servidor standalone do Next.js
CMD ["node", "server.js"]
