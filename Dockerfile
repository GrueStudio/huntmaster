FROM python:3.13.3-alpine

# Install dependencies first for better caching
RUN apk add --no-cache postgresql-client

# Create and set working directory
WORKDIR /app

# Copy only requirements first to leverage Docker cache
COPY ./app/requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000

ENV NAME HuntMaster

# The actual application code will be mounted via volume
