FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY . .
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine
ENV ACCOUNTS_URL=http://accounts:3000 \
    TRANSIT_URL=http://transit:8000 \
    NGINX_ENVSUBST_FILTER="^(ACCOUNTS_URL|TRANSIT_URL)$"
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/build /usr/share/nginx/html
EXPOSE 8080
