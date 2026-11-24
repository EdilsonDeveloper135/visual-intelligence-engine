# E2E runner (test profile only). Official Playwright image with matching browsers.
FROM mcr.microsoft.com/playwright:v1.65.1-noble
ENV npm_config_fund=false npm_config_audit=false npm_config_update_notifier=false
WORKDIR /e2e
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY playwright.config.ts ./
COPY specs ./specs
CMD ["npx", "playwright", "test"]
