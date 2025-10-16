"""
Main application entry point
"""
from app import create_app
from app.config import settings

app = create_app()

if __name__ == "__main__":
    app.run(
        host=settings.HOST,
        port=settings.PORT,
        debug=settings.DEBUG,
        threaded=True,
    )
