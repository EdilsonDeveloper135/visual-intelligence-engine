# Build stage (install phase only: needs the npm registry)
FROM node:24.22.3-alpine3.24@sha256:116b800c3754b440ee0aa3ed2f20f5bf3d99a554bfd9adeea09ea8017f6e85f5 AS build
ENV npm_config_fund=false npm_config_audit=false npm_config_update_notifier=false
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY . .
RUN npm run build \
 && mkdir -p dist/docs \
 && cp node_modules/swagger-ui-dist/swagger-ui.css node_modules/swagger-ui-dist/swagger-ui-bundle.js dist/docs/

FROM build AS test
CMD ["npx", "vitest", "run"]

# Runtime: static files + reverse proxy, unprivileged nginx, read-only filesystem
FROM nginxinc/nginx-unprivileged:1.30.6-alpine3.24@sha256:f5116ed4606f3eb015dd4a8e28cb9b351476dc0ad4bc6e9f93b19cec130cdf03 AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
