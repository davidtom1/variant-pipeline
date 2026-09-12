FROM python:3.12-slim

WORKDIR /app

# The pipeline has no third-party runtime dependencies; pytest is dev-only.
# If that changes, install requirements here, before copying source, so code
# edits don't invalidate the dependency layer.

COPY src/ src/

# Run as a non-root user. The uid is pinned so the mounted output directory
# has predictable ownership on the host.
RUN useradd --create-home --uid 1000 appuser
RUN mkdir -p /app/data/output && chown -R appuser:appuser /app/data
USER appuser

CMD ["python", "-m", "src.convert"]
