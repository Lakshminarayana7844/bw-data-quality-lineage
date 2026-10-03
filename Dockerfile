FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir pandas pyyaml
COPY bwdq ./bwdq
COPY config ./config
COPY data ./data
ENTRYPOINT ["python", "-m", "bwdq"]
CMD ["run", "--out", "/out"]
