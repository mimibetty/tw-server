import os

BASE_DIR = os.getcwd()
TEMPLATES_DIR = os.path.join(BASE_DIR, 'app', 'templates')

# Regex patterns for validation
PASSWORD_REGEX = (
    r'^(?=.*?[A-Z])(?=.*?[a-z])(?=.*?[0-9])(?=.*?[#?!@$%^&*-]).{8,}$'
)
OTP_CODE_REGEX = r'^[0-9]{6}$'
