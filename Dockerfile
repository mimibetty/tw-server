FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install system dependencies as root
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user and group
ARG USERNAME=appuser
ARG USER_UID=1000
ARG USER_GID=$USER_UID

RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME

# Create and set working directory with proper permissions
WORKDIR /server
RUN chown $USER_UID:$USER_GID /server

# Switch to non-root user
USER $USERNAME

# Add ~/.local/bin to PATH for the non-root user
ENV PATH="/home/${USERNAME}/.local/bin:${PATH}"

# Install Python dependencies
COPY --chown=$USER_UID:$USER_GID requirements.txt .
RUN python -m pip install --user --upgrade pip
RUN pip install --user --no-cache-dir -r requirements.txt
RUN pip install --user --no-cache-dir gunicorn

# Copy the rest of the application
COPY --chown=$USER_UID:$USER_GID . .

EXPOSE 8000
CMD ["gunicorn", "-c", "gunicorn.conf.py", "wsgi:app"]
