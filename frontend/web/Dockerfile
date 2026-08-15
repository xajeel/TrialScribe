FROM node:24.18.0-alpine AS build

WORKDIR /web

COPY frontend/web/package.json frontend/web/package-lock.json ./
RUN npm ci

COPY frontend/web/ .

ARG VITE_API_BASE_URL=http://127.0.0.1:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build

FROM nginx:1.30.4-alpine

COPY --from=build /web/dist /usr/share/nginx/html
COPY infra/release/nginx.conf /etc/nginx/conf.d/default.conf
