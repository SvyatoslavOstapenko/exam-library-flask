import os

from app import app
from models import db, Role, User, Genre, ReviewStatus


def remove_old_sqlite_db():
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')

    if not db_uri.startswith('sqlite:///'):
        return

    db_name = db_uri.replace('sqlite:///', '', 1)

    if os.path.isabs(db_name):
        db_path = db_name
    else:
        db_path = os.path.join(app.instance_path, db_name)

    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    if os.path.exists(db_path):
        os.remove(db_path)
        print(f'Старая база данных удалена: {db_path}')
    else:
        print(f'Старой базы данных не было: {db_path}')


def create_roles():
    admin_role = Role(
        name='Администратор',
        description='Суперпользователь, имеет полный доступ к системе, может создавать и удалять книги.'
    )

    moderator_role = Role(
        name='Модератор',
        description='Может редактировать данные книг и выполнять модерацию рецензий.'
    )

    user_role = Role(
        name='Пользователь',
        description='Может просматривать книги и оставлять рецензии.'
    )

    db.session.add_all([admin_role, moderator_role, user_role])
    db.session.flush()

    return admin_role, moderator_role, user_role


def create_review_statuses():
    statuses = [
        ReviewStatus(name='На рассмотрении'),
        ReviewStatus(name='Одобрена'),
        ReviewStatus(name='Отклонена'),
    ]

    db.session.add_all(statuses)


def create_genres():
    genres = [
        Genre(name='Роман'),
        Genre(name='Фантастика'),
        Genre(name='Детектив'),
        Genre(name='Научная литература'),
        Genre(name='История'),
        Genre(name='Программирование'),
    ]

    db.session.add_all(genres)


def create_users(admin_role, moderator_role, user_role):
    admin = User(
        login='admin',
        last_name='Администратор',
        first_name='Системы',
        middle_name='',
        role_id=admin_role.id,
    )
    admin.set_password('admin123')

    moderator = User(
        login='moderator',
        last_name='Модератор',
        first_name='Библиотеки',
        middle_name='',
        role_id=moderator_role.id,
    )
    moderator.set_password('moderator123')

    user = User(
        login='user',
        last_name='Иванов',
        first_name='Иван',
        middle_name='Иванович',
        role_id=user_role.id,
    )
    user.set_password('user123')

    db.session.add_all([admin, moderator, user])


def main():
    with app.app_context():
        remove_old_sqlite_db()

        db.create_all()

        admin_role, moderator_role, user_role = create_roles()
        create_review_statuses()
        create_genres()
        create_users(admin_role, moderator_role, user_role)

        db.session.commit()

        print('Новая база данных успешно создана.')
        print('Созданы роли: Администратор, Модератор, Пользователь.')
        print('Созданы статусы рецензий: На рассмотрении, Одобрена, Отклонена.')
        print('Созданы тестовые пользователи:')
        print('admin / admin123')
        print('moderator / moderator123')
        print('user / user123')


if __name__ == '__main__':
    main()