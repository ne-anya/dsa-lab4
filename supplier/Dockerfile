FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Непривилегированный пользователь (правило из лабораторной №1)
RUN useradd --create-home appuser
USER appuser

# Без оболочки sh: uvicorn сразу становится первым процессом контейнера
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]