# Use an official Python runtime as a parent image
FROM python:3.13.3-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# Using --no-cache-dir to reduce image size
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code, data, and assets into the container at /app
# This includes .py files, .json data files, and the media directory
COPY . .

# Make port 8501 available to the world outside this container (Streamlit's default port)
EXPOSE 8501

# Define environment variables for Streamlit server for proper container operation
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_SERVER_PORT=8501

# Run streamlit_app.py when the container launches
CMD ["streamlit", "run", "streamlit_app.py"]
