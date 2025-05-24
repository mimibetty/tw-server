# Server settings
bind = '0.0.0.0:8000'

# Logging settings
accesslog = '-'
errorlog = '-'
loglevel = 'info'
capture_output = True

# Worker settings
workers = 2
worker_class = 'eventlet'
worker_connections = 2000

# Timeout settings
timeout = 30
graceful_timeout = 30
keepalive = 2

# Worker Restart Settings
max_requests = 1000
max_requests_jitter = 50
