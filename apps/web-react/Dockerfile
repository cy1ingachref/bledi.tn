FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY . .
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.29-alpine

USER root
RUN apk upgrade --no-cache
# The stock mime.types has no .mjs entry; MapLibre's module worker would be
# served as application/octet-stream and rejected by the browser. Add mjs to
# the existing application/javascript types line, inside the types block.
RUN sed -i -E 's|(application/javascript[[:space:]]+)js;|\1js mjs;|' /etc/nginx/mime.types

ENV ACCOUNTS_URL=http://accounts:3000 \
    TRANSIT_URL=http://transit:8000 \
    ROUTING_URL=http://transit-routing:8081 \
    NGINX_ENVSUBST_FILTER="^(ACCOUNTS_URL|TRANSIT_URL|ROUTING_URL)$"
COPY rate-limit.conf /etc/nginx/conf.d/rate-limit.conf
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
USER nginx
EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
  CMD ["nginx", "-t"]
