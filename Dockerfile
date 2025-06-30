# syntax=docker/dockerfile:1

# Base image for all stages
FROM python:3.13-slim-bookworm AS base

# Builder stage - install dependencies and build tools
FROM base AS builder

# Copy uv from official image
COPY --from=ghcr.io/astral-sh/uv:0.7.17 /uv /uvx /bin/

# Set uv environment variables for optimal performance
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Set working directory
WORKDIR /app

# Install system dependencies needed for building Python packages
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    # Build tools
    gcc \
    g++ \
    git \
    cmake \
    meson \
    # Python development headers
    python3-dev \
    # Image processing libraries (for Pillow)
    libffi-dev \
    libfreetype6-dev \
    libfribidi-dev \
    libharfbuzz-dev \
    libjpeg62-turbo-dev \
    liblcms2-dev \
    libopenjp2-7-dev \
    libtiff5-dev \
    libwebp-dev \
    zlib1g-dev \
    # SSL and crypto
    libssl-dev \
    libsodium-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files first for better caching
COPY pyproject.toml uv.lock ./

# Install dependencies only (not the project itself)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Copy the rest of the application code
COPY . .

# Install the project itself
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Runtime stage - minimal image with only what's needed to run
FROM base AS runtime

# Install only runtime system dependencies
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    # Runtime libraries for image processing
    libfreetype6 \
    libfribidi0 \
    libharfbuzz0b \
    libjpeg62-turbo \
    liblcms2-2 \
    libopenjp2-7 \
    libtiff6 \
    libwebp7 \
    # For discord.py voice support (runtime versions)
    libffi8 \
    libsodium23 \
    # FFmpeg for audio processing
    ffmpeg \
    # SSL runtime
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy the virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY --from=builder /app/kidney-bot /app/kidney-bot
COPY --from=builder /app/lang /app/lang

# Set working directory
WORKDIR /app

# Make sure we use the virtual environment
ENV PATH="/app/.venv/bin:$PATH"

# Run the application
CMD ["python", "kidney-bot/main.py"]