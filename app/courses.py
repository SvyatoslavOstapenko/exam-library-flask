from __future__ import annotations

from flask import Blueprint, render_template, request, flash, redirect, url_for, abort
from flask_login import login_required, current_user
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from models import db, Course, Category, User, Review
from tools import CoursesFilter, ImageSaver

bp = Blueprint('courses', __name__, url_prefix='/courses')

COURSE_PARAMS = [
    'author_id', 'name', 'category_id', 'short_desc', 'full_desc'
]


def params():
    return {p: request.form.get(p) or None for p in COURSE_PARAMS}


def search_params():
    return {
        'name': request.args.get('name'),
        'category_ids': [x for x in request.args.getlist('category_ids') if x],
    }


def _recalc_course_rating(course_id: int) -> None:
    rating_sum, rating_num = db.session.execute(
        select(
            func.coalesce(func.sum(Review.rating), 0),
            func.count(Review.id),
        ).where(Review.course_id == course_id)
    ).one()

    course = db.session.get(Course, course_id)
    if course is None:
        abort(404)

    course.rating_sum = int(rating_sum or 0)
    course.rating_num = int(rating_num or 0)


def _get_my_review(course_id: int):
    if not current_user.is_authenticated:
        return None
    return db.session.scalar(
        select(Review).where(
            Review.course_id == course_id,
            Review.user_id == current_user.id,
        )
    )


@bp.route('/')
def index():
    courses_stmt = CoursesFilter(**search_params()).perform()
    pagination = db.paginate(courses_stmt)
    courses = pagination.items
    categories = db.session.execute(db.select(Category)).scalars()
    return render_template(
        'courses/index.html',
        courses=courses,
        categories=categories,
        pagination=pagination,
        search_params=search_params(),
    )


@bp.route('/new')
@login_required
def new():
    course = Course()
    categories = db.session.execute(db.select(Category)).scalars()
    users = db.session.execute(db.select(User)).scalars()
    return render_template(
        'courses/new.html',
        categories=categories,
        users=users,
        course=course,
    )


@bp.route('/create', methods=['POST'])
@login_required
def create():
    f = request.files.get('background_img')
    img = None
    course = Course()
    try:
        if f and f.filename:
            img = ImageSaver(f).save()

        image_id = img.id if img else None
        course = Course(**params(), background_image_id=image_id)
        db.session.add(course)
        db.session.commit()
    except IntegrityError as err:
        flash(
            f'Возникла ошибка при записи данных в БД. Проверьте корректность введённых данных. ({err})',
            'danger',
        )
        db.session.rollback()
        categories = db.session.execute(db.select(Category)).scalars()
        users = db.session.execute(db.select(User)).scalars()
        return render_template(
            'courses/new.html',
            categories=categories,
            users=users,
            course=course,
        )

    flash(f'Курс {course.name} был успешно добавлен!', 'success')
    return redirect(url_for('courses.index'))


@bp.route('/<int:course_id>')
def show(course_id: int):
    course = db.get_or_404(Course, course_id)

    last_reviews = db.session.scalars(
        select(Review)
        .where(Review.course_id == course_id)
        .options(selectinload(Review.user))
        .order_by(Review.created_at.desc())
        .limit(5)
    ).all()

    my_review = _get_my_review(course_id)

    return render_template(
        'courses/show.html',
        course=course,
        last_reviews=last_reviews,
        my_review=my_review,
    )


@bp.route('/<int:course_id>/reviews')
def reviews(course_id: int):
    course = db.get_or_404(Course, course_id)

    order = request.args.get('order', 'new')

    stmt = (
        select(Review)
        .where(Review.course_id == course_id)
        .options(selectinload(Review.user))
    )

    if order == 'positive':
        stmt = stmt.order_by(Review.rating.desc(), Review.created_at.desc())
    elif order == 'negative':
        stmt = stmt.order_by(Review.rating.asc(), Review.created_at.desc())
    else:
        order = 'new'
        stmt = stmt.order_by(Review.created_at.desc())

    pagination = db.paginate(stmt)
    reviews_list = pagination.items

    my_review = _get_my_review(course_id)

    return render_template(
        'courses/reviews.html',
        course=course,
        reviews=reviews_list,
        pagination=pagination,
        order=order,
        my_review=my_review,
    )


@bp.route('/<int:course_id>/reviews', methods=['POST'])
@login_required
def create_review(course_id: int):
    db.get_or_404(Course, course_id)

    existing = db.session.scalar(
        select(Review).where(
            Review.course_id == course_id,
            Review.user_id == current_user.id,
        )
    )
    if existing is not None:
        flash('Вы уже оставили отзыв к этому курсу.', 'warning')
        next_url = request.form.get('next')
        if next_url and next_url.startswith('/'):
            return redirect(next_url)
        return redirect(url_for('courses.show', course_id=course_id))

    try:
        rating = int(request.form.get('rating', '5'))
    except ValueError:
        rating = 5

    text = (request.form.get('text') or '').strip()

    if rating < 0 or rating > 5:
        flash('Оценка должна быть от 0 до 5.', 'danger')
        next_url = request.form.get('next')
        if next_url and next_url.startswith('/'):
            return redirect(next_url)
        return redirect(url_for('courses.show', course_id=course_id))

    if not text:
        flash('Текст отзыва не должен быть пустым.', 'danger')
        next_url = request.form.get('next')
        if next_url and next_url.startswith('/'):
            return redirect(next_url)
        return redirect(url_for('courses.show', course_id=course_id))

    review = Review(
        course_id=course_id,
        user_id=current_user.id,
        rating=rating,
        text=text,
    )

    try:
        db.session.add(review)
        _recalc_course_rating(course_id)
        db.session.commit()
    except IntegrityError as err:
        db.session.rollback()
        flash(f'Не удалось сохранить отзыв. ({err})', 'danger')
        next_url = request.form.get('next')
        if next_url and next_url.startswith('/'):
            return redirect(next_url)
        return redirect(url_for('courses.show', course_id=course_id))

    flash('Отзыв сохранён.', 'success')

    next_url = request.form.get('next')
    if next_url and next_url.startswith('/'):
        return redirect(next_url)

    return redirect(url_for('courses.show', course_id=course_id))