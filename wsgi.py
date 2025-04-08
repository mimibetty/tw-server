from app import AppContext
from app.environments import DevelopmentConfig

app = AppContext().get_app()

if __name__ == '__main__':
    app.config.from_object(DevelopmentConfig)
    app.run(host='0.0.0.0', port='8000')
