# TripWise - Backend Server

This is the backend server for the TripWise application, a comprehensive trip planning tool. It is built with Python and the Flask framework to provide a robust API for managing trip data, user information, and recommendation services.

## Prerequisites

- Python 3.12 or higher

## Getting Started

Follow these instructions to get the backend server up and running on your local machine for development and testing purposes.

### 1. Clone the Repository

```bash
git clone <your-repository-url>
cd tw-server
```

### 2. Set Up the Environment

Create and activate a virtual environment. This will isolate the project's dependencies from your system-wide Python packages.

- **On Windows:**
  ```bash
  python -m venv .venv
  .venv\Scripts\activate
  ```

- **On macOS/Linux:**
  ```bash
  python -m venv .venv
  source .venv/bin/activate
  ```

### 3. Install Dependencies

Install all the required packages using pip and the `requirements.txt` file.

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

The application requires certain environment variables to be set. Copy the example file and update it with your configuration.

```bash
cp .env.example .env
```
Now, edit the `.env` file with the necessary credentials and settings for your local environment (e.g., database URI, secret keys).

### 5. Set Up the Database

Before running the application, you need to apply the database migrations.

- **On Windows:**
  ```bash
  set FLASK_APP=wsgi.py
  flask db upgrade
  ```

- **On macOS/Linux:**
  ```bash
  export FLASK_APP='wsgi.py'
  flask db upgrade
  ```

## Running the Application

Once the setup is complete, you can start the Flask development server.

```bash
python wsgi.py
```

The server will start on the default port (usually 5000).

## Database Migrations

When you make changes to the database models (in `app/models.py`), you'll need to create a new migration script and apply it.

1.  **Generate a new migration:**
    ```bash
    # Set FLASK_APP environment variable if you haven't already
    flask db migrate -m "Your descriptive migration message"
    ```

2.  **Apply the migration:**
    ```bash
    flask db upgrade
    ```

This will update your database schema to reflect the latest model definitions.
