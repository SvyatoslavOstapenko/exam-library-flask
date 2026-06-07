from functools import wraps

from flask import Blueprint, render_template, request, flash, redirect, url_for, abort
from flask_login import login_required, current_user
from sqlalchemy import select, func
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import selectinload

from models import db, Book, Genre, Review, ReviewStatus
from tools import save_cover, delete_cover_file, sanitize_text, markdown_to_html


bp = Blueprint('books', __name__, url_prefix='/books')

PENDING_STATUS = 'На рассмотрении'
APPROVED_STATUS = 'Одобрена'
REJECTED_STATUS = 'Отклонена'

RATINGS = [
    (5, 'отлично'),
    (4, 'хорошо'),
    (3, 'удовлетворительно'),
    (2, 'неудовлетворительно'),
    (1, 'плохо'),
    (0, 'ужасно'),
]


def _role_name():
    if not current_user.is_authenticated or not current_user.role:
        return ''
    return current_user.role.name.lower()


def is_admin():
    return _role_name() in ('администратор', 'administrator', 'admin')


def is_moderator():
    return _role_name() in ('модератор', 'moderator')


def is_user():
    return _role_name() in ('пользователь', 'user')


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.is_authenticated and current_user.has_role(*roles):
                return view(*args, **kwargs)

            flash('У вас недостаточно прав для выполнения данного действия', 'danger')
            return redirect(url_for('index'))

        return wrapped

    return decorator


def _get_genres():
    return db.session.scalars(select(Genre).order_by(Genre.name)).all()


def _book_params():
    return {
        'title': (request.form.get('title') or '').strip(),
        'short_desc': sanitize_text(request.form.get('short_desc') or ''),
        'year': int(request.form.get('year') or 0),
        'publisher': (request.form.get('publisher') or '').strip(),
        'author': (request.form.get('author') or '').strip(),
        'pages': int(request.form.get('pages') or 0),
    }


def _validate_book_params(params, require_cover=False):
    errors = []

    if not params['title']:
        errors.append('Укажите название книги.')
    if not params['short_desc']:
        errors.append('Укажите краткое описание книги.')
    if params['year'] < 1:
        errors.append('Укажите корректный год выхода.')
    if not params['publisher']:
        errors.append('Укажите издательство.')
    if not params['author']:
        errors.append('Укажите автора.')
    if params['pages'] < 1:
        errors.append('Укажите корректный объём в страницах.')

    genre_ids = [int(x) for x in request.form.getlist('genre_ids') if x.isdigit()]
    if not genre_ids:
        errors.append('Выберите хотя бы один жанр.')

    cover_file = request.files.get('cover')
    if require_cover and (not cover_file or not cover_file.filename):
        errors.append('Загрузите обложку книги.')

    return errors


def _selected_genres():
    genre_ids = [int(x) for x in request.form.getlist('genre_ids') if x.isdigit()]
    if not genre_ids:
        return []

    return db.session.scalars(select(Genre).where(Genre.id.in_(genre_ids))).all()


def _get_status(name):
    return db.session.scalar(select(ReviewStatus).where(ReviewStatus.name == name))


def _approved_status_id():
    status = _get_status(APPROVED_STATUS)
    return status.id if status else None


def _pending_status_id():
    status = _get_status(PENDING_STATUS)
    return status.id if status else None


def _book_stats(book_id):
    approved_id = _approved_status_id()

    if approved_id is None:
        return {'avg': 0, 'count': 0}

    avg_rating, count_reviews = db.session.execute(
        select(
            func.coalesce(func.avg(Review.rating), 0),
            func.count(Review.id),
        ).where(
            Review.book_id == book_id,
            Review.status_id == approved_id,
        )
    ).one()

    return {
        'avg': float(avg_rating or 0),
        'count': int(count_reviews or 0),
    }


def _get_my_review(book_id):
    if not current_user.is_authenticated:
        return None

    return db.session.scalar(
        select(Review).where(
            Review.book_id == book_id,
            Review.user_id == current_user.id,
        )
    )


@bp.route('/')
def index():
    page = request.args.get('page', 1, type=int)

    stmt = select(Book).order_by(Book.year.desc(), Book.id.desc())
    pagination = db.paginate(stmt, page=page, per_page=10)

    books = pagination.items
    stats = {book.id: _book_stats(book.id) for book in books}

    return render_template(
        'books/index.html',
        books=books,
        pagination=pagination,
        stats=stats,
        is_admin=is_admin,
        is_moderator=is_moderator,
    )


@bp.route('/new')
@role_required('Администратор')
def new():
    book = Book()

    return render_template(
        'books/new.html',
        book=book,
        genres=_get_genres(),
        selected_genre_ids=[],
    )


@bp.route('/create', methods=['POST'])
@role_required('Администратор')
def create():
    book = Book()

    try:
        book_params = _book_params()
    except ValueError:
        flash(
            'При сохранении данных возникла ошибка. Проверьте корректность введённых данных.',
            'danger',
        )
        return render_template(
            'books/new.html',
            book=book,
            genres=_get_genres(),
            selected_genre_ids=[],
        )

    errors = _validate_book_params(book_params, require_cover=True)
    selected_genres = _selected_genres()

    if errors:
        for error in errors:
            flash(error, 'danger')

        for field, value in book_params.items():
            setattr(book, field, value)

        return render_template(
            'books/new.html',
            book=book,
            genres=_get_genres(),
            selected_genre_ids=[genre.id for genre in selected_genres],
        )

    try:
        book = Book(**book_params)
        book.genres = selected_genres

        db.session.add(book)
        db.session.flush()

        cover_file = request.files.get('cover')
        if cover_file and cover_file.filename:
            save_cover(cover_file, book.id)

        db.session.commit()

        flash('Книга успешно добавлена.', 'success')
        return redirect(url_for('books.show', book_id=book.id))

    except (SQLAlchemyError, OSError):
        db.session.rollback()

        flash(
            'При сохранении данных возникла ошибка. Проверьте корректность введённых данных.',
            'danger',
        )

        return render_template(
            'books/new.html',
            book=book,
            genres=_get_genres(),
            selected_genre_ids=[genre.id for genre in selected_genres],
        )


@bp.route('/<int:book_id>')
def show(book_id):
    book = db.get_or_404(Book, book_id)

    approved_id = _approved_status_id()

    reviews_stmt = (
        select(Review)
        .where(Review.book_id == book_id)
        .options(selectinload(Review.user), selectinload(Review.status))
        .order_by(Review.created_at.desc())
    )

    if approved_id is not None:
        reviews_stmt = reviews_stmt.where(Review.status_id == approved_id)
    else:
        reviews_stmt = reviews_stmt.where(False)

    reviews = db.session.scalars(reviews_stmt).all()
    my_review = _get_my_review(book_id)

    return render_template(
        'books/show.html',
        book=book,
        reviews=reviews,
        my_review=my_review,
        stats=_book_stats(book_id),
        markdown_to_html=markdown_to_html,
        is_admin=is_admin,
        is_moderator=is_moderator,
        is_user=is_user,
    )


@bp.route('/<int:book_id>/edit')
@role_required('Администратор', 'Модератор')
def edit(book_id):
    book = db.get_or_404(Book, book_id)

    return render_template(
        'books/edit.html',
        book=book,
        genres=_get_genres(),
        selected_genre_ids=[genre.id for genre in book.genres],
    )


@bp.route('/<int:book_id>/update', methods=['POST'])
@role_required('Администратор', 'Модератор')
def update(book_id):
    book = db.get_or_404(Book, book_id)

    try:
        book_params = _book_params()
    except ValueError:
        flash(
            'При сохранении данных возникла ошибка. Проверьте корректность введённых данных.',
            'danger',
        )
        return redirect(url_for('books.edit', book_id=book.id))

    selected_genres = _selected_genres()
    errors = _validate_book_params(book_params, require_cover=False)

    if errors:
        for error in errors:
            flash(error, 'danger')

        for field, value in book_params.items():
            setattr(book, field, value)

        return render_template(
            'books/edit.html',
            book=book,
            genres=_get_genres(),
            selected_genre_ids=[genre.id for genre in selected_genres],
        )

    try:
        for field, value in book_params.items():
            setattr(book, field, value)

        book.genres = selected_genres

        db.session.commit()

        flash('Данные книги успешно обновлены.', 'success')
        return redirect(url_for('books.show', book_id=book.id))

    except SQLAlchemyError:
        db.session.rollback()

        flash(
            'При сохранении данных возникла ошибка. Проверьте корректность введённых данных.',
            'danger',
        )

        return render_template(
            'books/edit.html',
            book=book,
            genres=_get_genres(),
            selected_genre_ids=[genre.id for genre in selected_genres],
        )


@bp.route('/<int:book_id>/delete', methods=['POST'])
@role_required('Администратор')
def delete(book_id):
    book = db.get_or_404(Book, book_id)
    title = book.title

    try:
        delete_cover_file(book.cover)
        db.session.delete(book)
        db.session.commit()

        flash(f'Книга «{title}» успешно удалена.', 'success')

    except SQLAlchemyError:
        db.session.rollback()
        flash('При удалении книги возникла ошибка.', 'danger')

    return redirect(url_for('books.index'))


@bp.route('/<int:book_id>/reviews/new')
@login_required
def new_review(book_id):
    book = db.get_or_404(Book, book_id)

    my_review = _get_my_review(book_id)
    if my_review:
        flash('Вы уже написали рецензию на эту книгу.', 'warning')
        return redirect(url_for('books.show', book_id=book.id))

    return render_template(
        'books/review_form.html',
        book=book,
        ratings=RATINGS,
    )


@bp.route('/<int:book_id>/reviews/create', methods=['POST'])
@login_required
def create_review(book_id):
    book = db.get_or_404(Book, book_id)

    if _get_my_review(book_id):
        flash('Вы уже написали рецензию на эту книгу.', 'warning')
        return redirect(url_for('books.show', book_id=book.id))

    pending_id = _pending_status_id()

    if pending_id is None:
        flash('Не найден статус рецензии «На рассмотрении».', 'danger')
        return redirect(url_for('books.show', book_id=book.id))

    try:
        rating = int(request.form.get('rating', 5))
    except ValueError:
        rating = 5

    text = sanitize_text(request.form.get('text') or '')

    if rating < 0 or rating > 5:
        flash('Оценка должна быть от 0 до 5.', 'danger')
        return render_template('books/review_form.html', book=book, ratings=RATINGS)

    if not text.strip():
        flash('Текст рецензии не должен быть пустым.', 'danger')
        return render_template('books/review_form.html', book=book, ratings=RATINGS)

    review = Review(
        book_id=book.id,
        user_id=current_user.id,
        rating=rating,
        text=text,
        status_id=pending_id,
    )

    try:
        db.session.add(review)
        db.session.commit()

        flash('Рецензия отправлена на рассмотрение.', 'success')
        return redirect(url_for('books.show', book_id=book.id))

    except IntegrityError:
        db.session.rollback()

        flash('Вы уже писали рецензию на эту книгу.', 'warning')
        return redirect(url_for('books.show', book_id=book.id))

    except SQLAlchemyError:
        db.session.rollback()

        flash('При сохранении рецензии возникла ошибка.', 'danger')
        return render_template('books/review_form.html', book=book, ratings=RATINGS)


@bp.route('/my-reviews')
@role_required('Пользователь')
def my_reviews():
    reviews = db.session.scalars(
        select(Review)
        .where(Review.user_id == current_user.id)
        .options(selectinload(Review.book), selectinload(Review.status))
        .order_by(Review.created_at.desc())
    ).all()

    return render_template(
        'books/my_reviews.html',
        reviews=reviews,
        markdown_to_html=markdown_to_html,
    )


@bp.route('/moderation/reviews')
@role_required('Администратор', 'Модератор')
def moderation_reviews():
    page = request.args.get('page', 1, type=int)

    pending_id = _pending_status_id()

    stmt = (
        select(Review)
        .options(selectinload(Review.book), selectinload(Review.user), selectinload(Review.status))
        .order_by(Review.created_at.asc())
    )

    if pending_id is not None:
        stmt = stmt.where(Review.status_id == pending_id)
    else:
        stmt = stmt.where(False)

    pagination = db.paginate(stmt, page=page, per_page=10)

    return render_template(
        'books/moderation.html',
        reviews=pagination.items,
        pagination=pagination,
    )


@bp.route('/moderation/reviews/<int:review_id>')
@role_required('Администратор', 'Модератор')
def moderation_review(review_id):
    review = db.get_or_404(Review, review_id)

    return render_template(
        'books/moderation_review.html',
        review=review,
        markdown_to_html=markdown_to_html,
    )


@bp.route('/moderation/reviews/<int:review_id>/approve', methods=['POST'])
@role_required('Администратор', 'Модератор')
def approve_review(review_id):
    review = db.get_or_404(Review, review_id)
    status = _get_status(APPROVED_STATUS)

    if status is None:
        abort(500)

    review.status_id = status.id
    db.session.commit()

    flash('Рецензия одобрена.', 'success')
    return redirect(url_for('books.moderation_reviews'))


@bp.route('/moderation/reviews/<int:review_id>/reject', methods=['POST'])
@role_required('Администратор', 'Модератор')
def reject_review(review_id):
    review = db.get_or_404(Review, review_id)
    status = _get_status(REJECTED_STATUS)

    if status is None:
        abort(500)

    review.status_id = status.id
    db.session.commit()

    flash('Рецензия отклонена.', 'success')
    return redirect(url_for('books.moderation_reviews'))