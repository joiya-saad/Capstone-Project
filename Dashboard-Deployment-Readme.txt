1. Create a .env file in the root directory that contains other scripts and files. 

In this file just define your Gemini API Key using one line command below:
GEMINI_API_KEY = "insert-your-key-here"


2. The process of containerizing the HR Mate AI application involves the following key steps:
A Dockerfile is created in the root directory of the project. This file is already provided in the root directory. In case
it is missing create one using details given below. This text file contains a set of instructions that Docker uses to build the application image. A typical Dockerfile for this Streamlit application would include:
o	Base Image: Specifying a base Python image (e.g., FROM python:3.9-slim).
o	Setting Working Directory: Defining a working directory within the image (e.g., WORKDIR /app).
o	Copying Requirements File: Copying the requirements.txt file into the image (e.g., COPY requirements.txt .).
o	Installing Dependencies: Running pip install -r requirements.txt --no-cache-dir to install all necessary Python libraries.
o	Copying Application Code: Copying the entire project directory (all Python scripts, data files like generated_employees.json, generated_projects.json, media assets, assets for CSS, .streamlit configuration) into the image's working directory (e.g., COPY . .).
o	Exposing Port: Specifying the port on which the Streamlit application will run (Streamlit defaults to 8501, e.g., EXPOSE 8501).
o	Defining Entrypoint/Command: Specifying the command to run when the container starts (e.g., CMD ["streamlit", "run", "streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]). The --server.address=0.0.0.0 makes the Streamlit app accessible from outside the container.


3.	Once the Dockerfile is prepared, the Docker image is built using the command:
docker build -t hr-mate-ai:latest

4.	This command, run in the project's root directory, creates an image tagged as hr-mate-ai with the version latest.

5. Image Transfer and Deployment on the Virtual Machine
-	Saving the Docker Image: After a successful build, the Docker image is saved as a .tar archive for easy transfer: 
docker save hr-mate-ai:latest > hr-mate-ai-latest.tar
-	Transferring to VM: The hr-mate-ai-latest.tar file is then transferred to the target Virtual Machine using a secure method like scp (Secure Copy Protocol) or any file transfer tool suitable for the VM environment.
-	Loading the Image on VM: On the VM (which must have Docker installed), the image is loaded from the .tar file:
docker load < hr-mate-ai-latest.tar
Running the Docker Container - The application is then run as a Docker container using a command similar to:
docker run -d -p 80:8501 \
    -v $(pwd)/chroma_db_vm:/app/chroma_db \
    -e GEMINI_API_KEY="your_actual_api_key" \
    --name hr-mate-container \ hr-mate-ai:latest	


o	-d: Runs the container in detached mode (in the background).
o	-p 80:8501: Maps port 80 on the VM's host to port 8501 inside the container (where Streamlit is running). This allows users to access the application via the VM's IP address or domain name on the standard HTTP port.
o	-v $(pwd)/chroma_db_vm:/app/chroma_db: This is a crucial volume mount. It maps a directory named chroma_db_vm (created in the current directory on the VM, e.g., where the docker run command is executed) to the /app/chroma_db directory inside the container. The CHROMA_DB_PATH within the application's config.py should be set to /app/chroma_db. This ensures that the ChromaDB data is persisted on the VM's filesystem, outside the container, and survives container restarts or updates.
o	-e GEMINI_API_KEY="your_actual_api_key": Passes the Google Gemini API key as an environment variable to the container. This is a secure way to provide secrets to the application running inside the container. Alternatively, Docker secrets or other environment management tools available on the VM could be used.
o	--name hr-mate-container: Assigns a recognizable name to the running container for easier management.
o	hr-mate-ai:latest: Specifies the image to run.

6. Accessing and Using the Deployed Application

Dockerized VM Deployment: Once the Docker container is running on the VM and port mapping is correctly configured 
(e.g., port 80 on VM to port 8501 in container), users can access the HR Mate AI application by navigating to the
 VM's public IP address or its assigned domain name in their web browser (e.g. http://<vm_ip_address>)
 for e.g. http://142.93.238.167:8501/  in our case.




