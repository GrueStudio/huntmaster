# Use an official Python runtime as a parent image
FROM python:3.13.3-alpine

# Copy the current directory contents into the container at /app
COPY ./app /huntmaster

RUN apk add --no-cache postgresql-client

# Set the working directory to /app
WORKDIR /huntmaster

# Install any needed packages specified in requirements.txt
# Install postgres client for alembic
RUN pip install --no-cache-dir -r /huntmaster/requirements.txt

# Make port 8000 available to the world outside this container
EXPOSE 8000

# Define environment variable
ENV NAME HuntMaster

# Create a non-root user
#RUN adduser --system --uid 1000 appuser #&& chown -R 1000 /app
# Switch to the non-root user
#USER appuser

# Run app.py when the container launches
CMD uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info

#CMD ["fastapi", "run", "app/main.py", "--port", "8000"]
