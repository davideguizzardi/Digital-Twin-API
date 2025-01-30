# Use the official Python image
FROM python:3.11

# Set the working directory
WORKDIR /app

# Copy the requirements file and install dependencies
COPY ./requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY api/ .

# Expose the FastAPI port (default is 8000)
EXPOSE 8000

# Run the FastAPI server
CMD ["python", "server.py"]
