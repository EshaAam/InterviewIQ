# syntax=docker/dockerfile:1
#
# The frontend in production: a Next.js standalone server, non-root.
#
#   docker build --build-arg NEXT_PUBLIC_API_URL=https://api.example.com/api/v1 \
#                -t interviewiq-web ./frontend
#
# NEXT_PUBLIC_API_URL is read at *build* time and inlined into the browser
# bundle — so each environment (staging, production) needs its own build.
# It is public by design: the browser has to know where the API is.

FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
# Exactly the lockfile; fail if it's out of date with package.json.
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /app
ARG NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS prod
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
# The standalone server, plus the two folders it doesn't copy by itself:
# static assets and public files (see Next's `output: "standalone"` docs).
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
COPY --from=build --chown=node:node /app/public ./public
# node:alpine ships an unprivileged `node` user (uid 1000).
USER node
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s --start-period=30s --start-interval=2s --retries=3 \
  CMD ["node", "-e", "fetch('http://127.0.0.1:3000/login').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]
CMD ["node", "server.js"]
