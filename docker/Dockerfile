# =============================================================================
# RLM API Service — Multi-stage Dockerfile
# Single image, different entrypoints for API server vs worker.
# =============================================================================

# -- Build stage --------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency manifest and install the rlm package + API deps
COPY pyproject.toml ./
COPY rlm/ ./rlm/

RUN pip install --no-cache-dir --prefix=/install . \
    && pip install --no-cache-dir --prefix=/install \
        "fastapi>=0.115.0" \
        "uvicorn[standard]>=0.32.0" \
        "redis[hiredis]>=5.2.0" \
        "pydantic-settings>=2.6.0"


# -- Runtime stage ------------------------------------------------------------
FROM python:3.12-slim AS runtime

# System deps for LocalREPL code execution
RUN apt-get update && apt-get install -y --no-install-recommends \
        wget curl git \
    && rm -rf /var/lib/apt/lists/*

# Common Python packages available to LocalREPL exec'd code
RUN pip install --no-cache-dir \
        numpy \
        pandas \
        scipy \
        sympy \
        requests \
        httpx \
        pyyaml \
        tqdm \
        python-dateutil \
        regex

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Application code
WORKDIR /app
COPY . .

# Non-root user
RUN useradd --create-home --shell /bin/bash rlm \
    && chown -R rlm:rlm /app
USER rlm

# Default: API server
EXPOSE 26030
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "26030"]
