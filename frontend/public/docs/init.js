// Self-hosted Swagger UI (no CDN). The spec is served by the local API.
window.ui = SwaggerUIBundle({
  url: "/api/v1/openapi.json",
  dom_id: "#swagger-ui",
  deepLinking: true,
  withCredentials: true,
  validatorUrl: null,
});
