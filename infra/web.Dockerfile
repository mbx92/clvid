FROM node:24.15.0-bookworm-slim@sha256:4e6b70dd6cbfc88c8157ba19aa3d9f9cce6ba4703576d55459e45efcbc9c5f5d AS javascript
FROM javascript AS remotion-build
WORKDIR /workspace/services/remotion
COPY services/remotion/package.json services/remotion/package-lock.json ./
RUN npm ci
COPY services/remotion/ ./
COPY services/backend/fonts/NotoSans-Regular.ttf ../backend/fonts/NotoSans-Regular.ttf
COPY services/backend/fonts/OFL.txt ../backend/fonts/OFL.txt
RUN npm run build

FROM javascript AS build
WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web/ ./
COPY --from=remotion-build /workspace/services/remotion/dist/player.js ./public/remotion/player.js
COPY --from=remotion-build /workspace/services/remotion/dist/THIRD-PARTY-NOTICES.txt ./public/remotion/THIRD-PARTY-NOTICES.txt
RUN npm run build

FROM node:24.15.0-bookworm-slim@sha256:4e6b70dd6cbfc88c8157ba19aa3d9f9cce6ba4703576d55459e45efcbc9c5f5d
ENV NODE_ENV=production HOST=0.0.0.0 PORT=3000
WORKDIR /app
COPY --from=build --chown=node:node /app/.output ./.output
USER node
EXPOSE 3000
CMD ["node", ".output/server/index.mjs"]
