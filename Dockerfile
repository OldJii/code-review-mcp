# Dockerfile for Code Review MCP Server
# Supports both stdio and SSE transports

# Build stage
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN pip install --no-cache-dir build

# Copy source files
COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/

# Build the package
RUN python -m build --wheel

# Runtime stage
FROM python:3.12-slim

LABEL org.opencontainers.image.title="Code Review MCP Server"
LABEL org.opencontainers.image.description="MCP Server for GitHub/GitLab code review"
LABEL org.opencontainers.image.source="https://github.com/OldJii/code-review-mcp"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser

# Copy built wheel from builder stage
COPY --from=builder /app/dist/*.whl /tmp/

# Install the package
RUN pip install --no-cache-dir /tmp/*.whl && \
    rm /tmp/*.whl

# Switch to non-root user
USER appuser

# Environment variables (can be overridden at runtime)
ENV GITHUB_TOKEN=""
ENV GITLAB_TOKEN=""
ENV GITLAB_HOST="gitlab.com"

# Default port for SSE transport
EXPOSE 8000

# Health check for SSE mode
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command: run with stdio transport
# Override with --transport sse for remote deployment
ENTRYPOINT ["code-review-mcp"]
CMD ["--transport", "stdio"]
