FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN groupadd --gid 10001 trqbec && useradd --uid 10001 --gid trqbec --create-home trqbec
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY migrations ./migrations
RUN python -m pip install --upgrade pip && python -m pip install .

USER 10001:10001
EXPOSE 8787
CMD ["trq-bec-api"]
