import os

BASE_DIR = os.getcwd()
TEMPLATES_DIR = os.path.join(BASE_DIR, 'app', 'templates')

# Pagination
DEFAULT_PAGINATION_LIMIT = 10
MAX_PAGINATION_LIMIT = 50

# Regex patterns for validation
PASSWORD_REGEX = (
    r'^(?=.*?[A-Z])(?=.*?[a-z])(?=.*?[0-9])(?=.*?[#?!@$%^&*-]).{8,}$'
)
OTP_CODE_REGEX = r'^[0-9]{6}$'
