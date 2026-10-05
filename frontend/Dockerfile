FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json ./
COPY package-lock.json* ./
# The verification is part of the same layer on purpose. npm can fail to
# reach the registry — a broken docker0 bridge leaves builds with no network —
# and still exit 0, leaving package folders empty. Docker then caches that as a
# good layer and the failure surfaces three steps later as "next: not found".
# Checking here makes the install itself fail, and nothing broken is cached.
RUN npm install --legacy-peer-deps \
    && node_modules/.bin/next --version

ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

COPY . .
RUN npm run build

FROM node:20-alpine AS runner

WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/public ./public

EXPOSE 3000
CMD ["npm", "run", "start"]
