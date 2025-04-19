# TripWise - Flask

## Pre-requisites

-   Python 3.12+

## Installation

### Create and activate a virtual environment

-   On Windows:

```bash
python -m venv venv
venv\Scripts\activate
```

-   On macOS/Linux:

```bash
python -m venv venv
source venv/bin/activate
```

### Install the required packages

```bash
pip install -r requirements.txt
```

### Set up the database

```bash
export FLASK_APP='wsgi.py'
flask db upgrade
```

### Run the application

```bash
python wsgi.py
```

### Make new migrations

```bash
export FLASK_APP='wsgi.py'
flask db migrate -m "<MIGRATION_MESSAGE>"
flask db upgrade
```
