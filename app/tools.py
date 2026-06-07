import hashlib
import os

import bleach
import markdown
from flask import current_app
from markupsafe import Markup
from werkzeug.utils import secure_filename

from models import db, Cover


ALLOWED_TAGS = list(bleach.sanitizer.ALLOWED_TAGS) + [
    'p', 'br', 'pre', 'code', 'h1', 'h2', 'h3',
    'h4', 'h5', 'h6', 'ul', 'ol', 'li',
    'strong', 'em', 'blockquote'
]

ALLOWED_ATTRIBUTES = {
    **bleach.sanitizer.ALLOWED_ATTRIBUTES,
    'a': ['href', 'title'],
}


def sanitize_text(text):
    return bleach.clean(
        text or '',
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        strip=True,
    )


def markdown_to_html(text):
    html = markdown.markdown(
        text or '',
        extensions=['extra', 'nl2br'],
    )

    safe_html = bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        strip=True,
    )

    return Markup(safe_html)


def calculate_md5(file):
    md5_hash = hashlib.md5(file.read()).hexdigest()
    file.seek(0)
    return md5_hash


def save_cover(file, book_id):
    os.makedirs(current_app.config['UPLOAD_FOLDER'], exist_ok=True)

    md5_hash = calculate_md5(file)

    existing_cover = db.session.execute(
        db.select(Cover).filter_by(md5_hash=md5_hash)
    ).scalar()

    file_name = secure_filename(file.filename)

    if existing_cover:
        file_name = existing_cover.file_name

    cover = Cover(
        file_name=file_name,
        mime_type=file.mimetype,
        md5_hash=md5_hash,
        book_id=book_id,
    )

    db.session.add(cover)
    db.session.flush()

    file_path = os.path.join(
        current_app.config['UPLOAD_FOLDER'],
        cover.storage_filename,
    )

    if not os.path.exists(file_path):
        file.save(file_path)

    return cover


def delete_cover_file(cover):
    if not cover:
        return

    same_files_count = db.session.execute(
        db.select(db.func.count(Cover.id)).filter_by(md5_hash=cover.md5_hash)
    ).scalar()

    if same_files_count and same_files_count > 1:
        return

    file_path = os.path.join(
        current_app.config['UPLOAD_FOLDER'],
        cover.storage_filename,
    )

    if os.path.exists(file_path):
        os.remove(file_path)