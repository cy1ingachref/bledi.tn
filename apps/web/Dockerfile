FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY . .
RUN npm run build

# 1.29-alpine sits on alpine 3.23. The previous 1.27-alpine was on 3.21, whose
# openssl, c-ares and curl had all picked up HIGH/CRITICAL advisories by now.
FROM nginxinc/nginx-unprivileged:1.29-alpine

# The base tag is rebuilt when nginx releases, not when alpine ships a patch, so
# pull the security updates that landed since it was built. Needs root; the
# image drops to the nginx user for the server itself.
USER root
RUN apk upgrade --no-cache

ENV ACCOUNTS_URL=http://accounts:3000 \
    TRANSIT_URL=http://transit:8000 \
    NGINX_ENVSUBST_FILTER="^(ACCOUNTS_URL|TRANSIT_URL)$"
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/build /usr/share/nginx/html
USER nginx
EXPOSE 8080
