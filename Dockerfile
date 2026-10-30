# Shared image for the `indexer` and `app` services.

FROM python:3.12-slim AS builder
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
WORKDIR /build
COPY pyproject.toml ./
COPY roboost_rag ./roboost_rag
RUN pip install --no-cache-dir .

FROM python:3.12-slim
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
RUN useradd --create-home roboost
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY ui ./ui
COPY tests/eval ./tests/eval
USER roboost
EXPOSE 8501
CMD ["python", "-m", "roboost_rag", "check"]
