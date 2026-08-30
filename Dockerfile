# A Dockerfile is a recipe for building a container image: a self-contained
# package with Python, our code, and all dependencies installed, so it runs
# identically on your laptop and on Cloud Run.

# Start from an official slim Python image rather than a full OS image —
# smaller image = faster builds, faster deploys, smaller attack surface.
FROM python:3.12-slim

# All subsequent commands (COPY, RUN, CMD) happen relative to this directory
# inside the container.
WORKDIR /app

# Copy just the requirements file first, before the rest of the code.
# This is a deliberate ordering trick: Docker caches each layer, and only
# rebuilds a layer (and everything after it) if its inputs changed. Since
# requirements.txt changes far less often than your source code, this means
# `pip install` only reruns when you actually add/change a dependency —
# not on every single code change, which speeds up rebuilds a lot.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the rest of the application code.
COPY src/ ./src/
COPY schemas/ ./schemas/

# Cloud Run Jobs pass configuration as environment variables (set later via
# `gcloud run jobs create --set-env-vars` or `--set-secrets`), not a .env
# file — so we deliberately do NOT copy .env into the image. python-dotenv's
# load_dotenv() simply finds nothing and no-ops, and the real env vars Cloud
# Run injects at runtime take over instead.

# The command that runs when the container starts. Cloud Run Jobs run this
# once to completion, then the container exits.
CMD ["python", "-m", "src.run_pipeline"]
