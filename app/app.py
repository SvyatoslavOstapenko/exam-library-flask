from flask import Flask, send_from_directory, redirect, url_for
from flask_migrate import Migrate
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.middleware.proxy_fix import ProxyFix

from models import db, Cover
from auth import bp as auth_bp, init_login_manager
from books import bp as books_bp


app = Flask(__name__)
application = app

app.config.from_pyfile('config.py')
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1, x_prefix=1)

db.init_app(app)
migrate = Migrate(app, db)

init_login_manager(app)


@app.errorhandler(SQLAlchemyError)
def handle_sqlalchemy_error(err):
    error_msg = (
        'Возникла ошибка при подключении к базе данных. '
        'Повторите попытку позже.'
    )
    return f'{error_msg} (Подробнее: {err})', 500


app.register_blueprint(auth_bp)
app.register_blueprint(books_bp)


@app.route('/')
def index():
    return redirect(url_for('books.index'))


@app.route('/covers/<int:cover_id>')
def cover(cover_id):
    cover_obj = db.get_or_404(Cover, cover_id)

    return send_from_directory(
        app.config['UPLOAD_FOLDER'],
        cover_obj.storage_filename
    )