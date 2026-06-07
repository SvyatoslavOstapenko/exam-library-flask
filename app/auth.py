from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import LoginManager, login_user, logout_user, login_required

from models import db, User


bp = Blueprint('auth', __name__, url_prefix='/auth')


def init_login_manager(app):
    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.login_message = (
        'Для выполнения данного действия необходимо пройти процедуру аутентификации'
    )
    login_manager.login_message_category = 'warning'
    login_manager.user_loader(load_user)
    login_manager.init_app(app)


def load_user(user_id):
    return db.session.get(User, int(user_id))


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login = request.form.get('login')
        password = request.form.get('password')
        remember = bool(request.form.get('remember'))

        if login and password:
            user = db.session.execute(
                db.select(User).filter_by(login=login)
            ).scalar()

            if user and user.check_password(password):
                login_user(user, remember=remember)
                flash('Вы успешно вошли в систему.', 'success')
                next_url = request.args.get('next')
                return redirect(next_url or url_for('index'))

        flash(
            'Невозможно аутентифицироваться с указанными логином и паролем',
            'danger'
        )

    return render_template('auth/login.html')


@bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы вышли из системы.', 'success')
    return redirect(request.referrer or url_for('index'))