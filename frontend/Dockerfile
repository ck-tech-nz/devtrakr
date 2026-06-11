FROM node:24-alpine AS builder

WORKDIR /app

ARG NUXT_API_BASE=http://backend:8000
ENV NUXT_API_BASE=${NUXT_API_BASE}

COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:24-alpine

WORKDIR /app

COPY --from=builder /app/.output .output

ENV HOST=0.0.0.0
ENV PORT=3000

EXPOSE 3000

CMD ["node", ".output/server/index.mjs"]
