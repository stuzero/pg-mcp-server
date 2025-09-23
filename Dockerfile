# Dockerfile
FROM python:3.13-slim

WORKDIR /app

# The installer requires curl (and certificates) to download the release archive
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates

# Download the latest uv installer
ADD https://astral.sh/uv/install.sh /uv-installer.sh

# Run the installer then remove it
RUN sh /uv-installer.sh && rm /uv-installer.sh

# Ensure the installed binary is on the `PATH`
ENV PATH="/root/.local/bin/:$PATH"

# Copy the project into the image
ADD . /app
COPY .profile /root/.profile

# Sync the project into a new environment, using the frozen lockfile
RUN cd /app && rm -r .venv && uv sync --frozen

# Run the application
CMD ["uv", "run", "-m", "server.app"]
