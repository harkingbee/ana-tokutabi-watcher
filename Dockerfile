FROM python:3.12-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml README.md ./
COPY src/ src/
COPY config.example.yaml ./

RUN uv pip install --system -e .

# dataディレクトリ
RUN mkdir -p /app/data

ENV TZ=Asia/Tokyo
ENV PYTHONUNBUFFERED=1

CMD ["ana-tokutabi", "run-scheduler"]
