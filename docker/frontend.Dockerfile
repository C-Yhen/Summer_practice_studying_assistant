ARG NODE_IMAGE=public.ecr.aws/docker/library/node:22-alpine
ARG NGINX_IMAGE=public.ecr.aws/docker/library/nginx:1.27-alpine
FROM ${NODE_IMAGE} AS builder

WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./

ARG VITE_API_BASE_URL=/api/v1
ARG VITE_WS_URL=/api/v1/ws/tasks
ARG VITE_ENABLE_MOCK=false
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_WS_URL=$VITE_WS_URL \
    VITE_ENABLE_MOCK=$VITE_ENABLE_MOCK
RUN npm run build

FROM ${NGINX_IMAGE}
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
