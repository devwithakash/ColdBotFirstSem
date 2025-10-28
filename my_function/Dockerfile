# my_function/Dockerfile
FROM python:3.10-slim

WORKDIR /app

# We need Flask to run the server
RUN pip install flask

COPY app.py .

# --- ADD THIS LINE ---
EXPOSE 5000
# ---

# The command to run when the container starts
CMD ["python", "app.py"]