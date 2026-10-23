# BIOTORF Business OS · frontend (Vue 3 → статика, отдаётся nginx)
FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci 2>/dev/null || npm install

COPY . .

# Пустной VITE_COMMS_API => фронт сам определит бэкенд по текущему хосту
ARG VITE_COMMS_API=""
ENV VITE_COMMS_API=$VITE_COMMS_API
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
