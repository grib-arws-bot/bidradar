# 정적 빌드(Vite) + nginx로 서빙 — ARWS admin-page-v2 패턴 복제(의사결정_로그 6번).
# 브라우저는 이 컨테이너 하나만 보고, /api는 nginx가 backend 컨테이너로 리버스 프록시한다
# (nginx.conf 참고) — CORS 설정 자체가 불필요.
FROM node:20.18.1-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27.3-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
