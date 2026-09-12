# Base image. "slim" is the smaller variant — ~50MB instead of ~350MB for the
# full image. Match the Python version you develop with.
FROM python:3.12-slim

# Where the code lives inside the container. Everything after this is relative
# to it, so "COPY src/ src/" lands at /app/src.
WORKDIR /app

# --- Layer caching ---
# Dependencies change rarely, source changes constantly. Copying and installing
# requirements FIRST means editing a .py file doesn't re-run pip on rebuild.
# YOUR CODE: copy requirements.txt and pip install it
#   COPY requirements.txt .
#   RUN pip install --no-cache-dir -r requirements.txt
#   (--no-cache-dir keeps pip's download cache out of the image)

# Now the source. This layer rebuilds on every code change, which is fine
# because it's fast.
COPY src/ src/

# --- Non-root user ---
# Containers run as root by default. If the process is compromised, root inside
# the container is a much better starting point for an attacker than a normal
# user. The rubric asks for this explicitly.
RUN useradd --create-home --shell /bin/bash appuser

# The container writes to /app/data/output, which will be a mounted volume.
# Create it and hand ownership to appuser BEFORE switching, since appuser
# can't chown anything itself.
RUN mkdir -p /app/data/output && chown -R appuser:appuser /app/data

USER appuser

# What runs when the container starts. Uses the module form so Python resolves
# the "src." imports correctly, same as you run it locally.
CMD ["python", "-m", "src.convert"]