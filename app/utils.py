def create_paging(
    data: list, page: int, size: int, offset: int, total_count: int
):
    page_count = (total_count // size) + (1 if total_count % size > 0 else 0)

    return {
        'data': data,
        'paging': {
            'page': page,
            'size': size,
            'offset': offset,
            'totalCount': total_count,
            'pageCount': page_count,
        },
    }


def execute_neo4j_query(query: str, params: dict = None):
    from neo4j import GraphDatabase

    from .environments import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USERNAME

    driver = GraphDatabase.driver(
        NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD)
    )
    try:
        with driver.session() as session:
            result = session.run(query, params)
            if 'RETURN' in query.upper():
                return result.data()
    except Exception as e:
        raise e
    finally:
        driver.close()


def send_async_email(recipients: list[str], subject: str, html: str):
    from threading import Thread

    from flask_mail import Message

    from . import AppContext
    from .extensions import mail

    def send_email(message: Message):
        app = AppContext().get_app()
        with app.app_context():
            mail.send(message)

    # Create a new message
    message = Message(subject=subject, recipients=recipients)
    message.html = html

    # Start a new thread to send the email
    thread = Thread(target=send_email, args=(message,))
    thread.start()


def get_redis():
    from . import AppContext

    return AppContext().get_redis()
