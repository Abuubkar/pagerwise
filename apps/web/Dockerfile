# The on-call UI as a standalone Next.js server (next.config.ts sets output: "standalone").
FROM node:24-slim@sha256:c86ecead9e55a5210ac1727de38a4ca840bf03dcaf34dc9749addbf383b1920c AS build
RUN npm install --global pnpm@11.15.0
WORKDIR /web
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store pnpm install --frozen-lockfile
COPY . .
# Next bakes rewrites and NEXT_PUBLIC_* values in at build time: where the API is, from the server and the browser.
ARG API_URL=http://api:8001
ARG NEXT_PUBLIC_GRAPHQL_WS=ws://localhost:8001/graphql
ENV API_URL=${API_URL} NEXT_PUBLIC_GRAPHQL_WS=${NEXT_PUBLIC_GRAPHQL_WS} NEXT_TELEMETRY_DISABLED=1
RUN pnpm build

FROM node:24-slim@sha256:c86ecead9e55a5210ac1727de38a4ca840bf03dcaf34dc9749addbf383b1920c
WORKDIR /web
ENV NODE_ENV=production PORT=3001 HOSTNAME=0.0.0.0 NEXT_TELEMETRY_DISABLED=1
COPY --from=build --chown=node:node /web/.next/standalone ./
COPY --from=build --chown=node:node /web/.next/static ./.next/static
USER node
EXPOSE 3001
CMD ["node", "server.js"]
