import os
import secrets
from datetime import datetime, timedelta
from functools import wraps

import cloudinary
import cloudinary.uploader
import resend

from flask import (
    Flask, render_template, request, jsonify,
    redirect, url_for, flash, abort, session
)
from flask_login import (
    LoginManager, login_user, logout_user,
    login_required, current_user
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

from models import db, User, File, Message, Payment

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)

DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///amber.db')
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql+psycopg://', 1)
elif DATABASE_URL.startswith('postgresql://'):
    DATABASE_URL = DATABASE_URL.replace('postgresql://', 'postgresql+psycopg://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'error'

limiter = Limiter(get_remote_address, app=app, storage_uri='memory://', default_limits=[],
                  enabled=not os.environ.get('FLASK_TESTING'))

resend.api_key = os.environ.get('RESEND_API_KEY', '')

cloudinary.config(
    cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME', ''),
    api_key=os.environ.get('CLOUDINARY_API_KEY', ''),
    api_secret=os.environ.get('CLOUDINARY_API_SECRET', '')
)

ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', '').lower()

ALLOWED_EXTENSIONS = {
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
    'txt', 'csv', 'png', 'jpg', 'jpeg', 'gif', 'zip'
}

if not os.environ.get('FLASK_TESTING'):
    with app.app_context():
        db.create_all()


# ── Helpers ──

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def notify_admin(subject, body):
    recipient = os.environ.get('MAIL_RECIPIENT')
    if not recipient or not resend.api_key:
        return
    try:
        resend.Emails.send({
            'from': 'Amber Portal <onboarding@resend.dev>',
            'to': recipient,
            'subject': subject,
            'text': body,
        })
    except Exception as e:
        app.logger.warning('Admin notification failed: %s', e)


def notify_client(client_email, subject, body):
    if not resend.api_key:
        return
    try:
        resend.Emails.send({
            'from': 'Amber Consulting <onboarding@resend.dev>',
            'to': client_email,
            'subject': subject,
            'text': body,
        })
    except Exception as e:
        app.logger.warning('Client notification failed: %s', e)


@app.template_filter('download_url')
def download_url(cloudinary_url):
    return cloudinary_url.replace('/upload/', '/upload/fl_attachment/', 1)


# ── Public routes ──

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/contact', methods=['POST'])
def contact():
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    message = request.form.get('message', '').strip()

    if not name or not email or not message:
        return jsonify({'success': False, 'error': 'All fields are required.'}), 400

    try:
        recipient = os.environ['MAIL_RECIPIENT']
        resend.Emails.send({
            'from': 'Amber Consulting <onboarding@resend.dev>',
            'to': recipient,
            'subject': f'New contact form message from {name}',
            'text': f'Name: {name}\nEmail: {email}\n\nMessage:\n{message}',
        })
        return jsonify({'success': True})
    except KeyError as e:
        app.logger.error('Missing environment variable: %s', e)
        return jsonify({'success': False, 'error': 'Server misconfiguration.'}), 500
    except Exception as e:
        app.logger.error('Email send failed: %s', e)
        return jsonify({'success': False, 'error': 'Failed to send message. Please try again later.'}), 500


# ── Auth routes ──

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit('10 per minute')
def login():
    if request.args.get('timeout'):
        flash('You were logged out due to inactivity.', 'error')

    if current_user.is_authenticated:
        return redirect(url_for('admin' if current_user.role == 'admin' else 'dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            session.permanent = True
            next_page = request.args.get('next')
            return redirect(next_page or url_for('admin' if user.role == 'admin' else 'dashboard'))

        flash('Invalid email or password.', 'error')

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        name = request.form.get('name', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')

        if not email or not name or not password:
            flash('All fields are required.', 'error')
            return render_template('register.html')
        if password != confirm:
            flash('Passwords do not match.', 'error')
            return render_template('register.html')
        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
            return render_template('register.html')
        if User.query.filter_by(email=email).first():
            flash('An account with this email already exists.', 'error')
            return render_template('register.html')

        role = 'admin' if ADMIN_EMAIL and email == ADMIN_EMAIL else 'client'
        user = User(
            email=email,
            name=name,
            password_hash=generate_password_hash(password),
            role=role
        )
        db.session.add(user)
        db.session.commit()
        login_user(user)
        session.permanent = True
        return redirect(url_for('admin' if role == 'admin' else 'dashboard'))

    return render_template('register.html')


@app.route('/logout')
def logout():
    logout_user()
    timeout = request.args.get('timeout')
    return redirect(url_for('login', timeout=1) if timeout else url_for('index'))


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first()
        if user:
            token = secrets.token_urlsafe(32)
            user.reset_token = token
            user.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
            db.session.commit()
            reset_url = request.host_url.rstrip('/') + url_for('reset_password', token=token)
            notify_client(user.email, 'Reset Your Password — Amber Consulting',
                f'Hi {user.name},\n\nClick the link below to reset your password (expires in 1 hour):\n\n{reset_url}\n\nIf you did not request this, ignore this email.')
        # Always show success to prevent email enumeration
        flash('If that email is registered, a reset link has been sent.', 'success')
        return redirect(url_for('login'))
    return render_template('forgot_password.html')


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    user = User.query.filter_by(reset_token=token).first()
    if not user or not user.reset_token_expires or user.reset_token_expires < datetime.utcnow():
        flash('Invalid or expired reset link.', 'error')
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
            return render_template('reset_password.html', token=token)
        if password != confirm:
            flash('Passwords do not match.', 'error')
            return render_template('reset_password.html', token=token)
        user.password_hash = generate_password_hash(password)
        user.reset_token = None
        user.reset_token_expires = None
        db.session.commit()
        flash('Password updated. Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('reset_password.html', token=token)


# ── Client dashboard ──

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'admin':
        return redirect(url_for('admin'))

    # Mark all admin messages as read
    Message.query.filter_by(
        user_id=current_user.id, sender_role='admin', is_read=False
    ).update({'is_read': True})
    db.session.commit()

    files = File.query.filter_by(user_id=current_user.id).order_by(File.uploaded_at.desc()).all()
    messages = Message.query.filter_by(user_id=current_user.id).order_by(Message.created_at.asc()).all()
    payments = Payment.query.filter_by(user_id=current_user.id).order_by(Payment.created_at.desc()).all()
    unread_count = Message.query.filter_by(user_id=current_user.id, sender_role='admin', is_read=False).count()
    pending_count = sum(1 for p in payments if p.status == 'pending')

    return render_template('dashboard.html',
        files=files, messages=messages, payments=payments,
        unread_count=unread_count, pending_count=pending_count)


@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files or not request.files['file'].filename:
        flash('No file selected.', 'error')
        return redirect(url_for('dashboard') + '#files')

    f = request.files['file']
    if not allowed_file(f.filename):
        flash(f'File type not allowed. Accepted: {", ".join(sorted(ALLOWED_EXTENSIONS))}', 'error')
        return redirect(url_for('dashboard') + '#files')

    try:
        result = cloudinary.uploader.upload(
            f,
            resource_type='auto',
            folder=f'amber-consulting/{current_user.id}',
            use_filename=True,
            unique_filename=True
        )
        db.session.add(File(
            user_id=current_user.id,
            filename=f.filename,
            cloudinary_url=result['secure_url'],
            cloudinary_public_id=result['public_id']
        ))
        db.session.commit()
        notify_admin(
            f'New file uploaded by {current_user.name}',
            f'{current_user.name} ({current_user.email}) uploaded a file:\n\n{f.filename}'
        )
        flash('File uploaded successfully.', 'success')
    except Exception as e:
        app.logger.error('Upload failed: %s', e)
        flash('Upload failed. Please try again.', 'error')

    return redirect(url_for('dashboard') + '#files')


@app.route('/download/<int:file_id>')
@login_required
def download_file(file_id):
    if current_user.role == 'admin':
        f = db.session.get(File, file_id) or abort(404)
    else:
        f = File.query.filter_by(id=file_id, user_id=current_user.id).first_or_404()

    try:
        import urllib.request
        with urllib.request.urlopen(f.cloudinary_url) as resp:
            data = resp.read()
        from flask import Response
        return Response(
            data,
            headers={
                'Content-Disposition': f'attachment; filename="{f.filename}"',
                'Content-Type': 'application/octet-stream',
            }
        )
    except Exception as e:
        app.logger.error('Download failed: %s', e)
        flash('Download failed. Please try again.', 'error')
        return redirect(url_for('dashboard'))


@app.route('/files/<int:file_id>/delete', methods=['POST'])
@login_required
def delete_file(file_id):
    f = File.query.filter_by(id=file_id, user_id=current_user.id).first_or_404()
    try:
        cloudinary.uploader.destroy(f.cloudinary_public_id, resource_type='raw')
    except Exception as e:
        app.logger.warning('Cloudinary delete failed: %s', e)
    db.session.delete(f)
    db.session.commit()
    flash('File deleted.', 'success')
    return redirect(url_for('dashboard') + '#files')


@app.route('/messages/send', methods=['POST'])
@login_required
def send_message():
    content = request.form.get('content', '').strip()
    if content:
        db.session.add(Message(
            user_id=current_user.id,
            sender_role='client',
            sender_name=current_user.name,
            content=content
        ))
        db.session.commit()
        notify_admin(
            f'New message from {current_user.name}',
            f'{current_user.name} ({current_user.email}) sent a message:\n\n{content}'
        )
    return redirect(url_for('dashboard') + '#messages')


@app.route('/payments/<int:payment_id>/pay', methods=['POST'])
@login_required
def make_payment(payment_id):
    payment = Payment.query.filter_by(
        id=payment_id, user_id=current_user.id, status='pending'
    ).first_or_404()
    payment.status = 'paid'
    payment.paid_at = datetime.utcnow()
    db.session.commit()
    flash(f'Payment of ${payment.amount:,.2f} processed successfully.', 'success')
    return redirect(url_for('dashboard') + '#payments')


# ── Admin routes ──

@app.route('/admin')
@login_required
@admin_required
def admin():
    clients = User.query.filter_by(role='client').order_by(User.created_at.desc()).all()
    selected_client = None
    files, messages, payments = [], [], []

    # Overview stats (always computed)
    total_clients = len(clients)
    pending_payments = Payment.query.filter_by(status='pending').all()
    pending_count = len(pending_payments)
    pending_amount = sum(p.amount for p in pending_payments)
    unread_from_clients = Message.query.filter_by(sender_role='client', is_read=False).count()
    recent_files = db.session.query(File, User).join(User, File.user_id == User.id)\
        .order_by(File.uploaded_at.desc()).limit(6).all()
    recent_messages = db.session.query(Message, User).join(User, Message.user_id == User.id)\
        .filter(Message.sender_role == 'client').order_by(Message.created_at.desc()).limit(6).all()

    stats = dict(
        total_clients=total_clients,
        pending_count=pending_count,
        pending_amount=pending_amount,
        unread_from_clients=unread_from_clients,
        recent_files=recent_files,
        recent_messages=recent_messages,
    )

    client_id = request.args.get('client_id', type=int)
    if client_id:
        selected_client = User.query.filter_by(id=client_id, role='client').first_or_404()
        # Mark client messages as read
        Message.query.filter_by(
            user_id=client_id, sender_role='client', is_read=False
        ).update({'is_read': True})
        db.session.commit()

        files = File.query.filter_by(user_id=client_id).order_by(File.uploaded_at.desc()).all()
        messages = Message.query.filter_by(user_id=client_id).order_by(Message.created_at.asc()).all()
        payments = Payment.query.filter_by(user_id=client_id).order_by(Payment.created_at.desc()).all()

    # Unread counts per client for sidebar badges
    unread_per_client = {
        row.user_id: row.count
        for row in db.session.query(Message.user_id, db.func.count().label('count'))
            .filter_by(sender_role='client', is_read=False)
            .group_by(Message.user_id).all()
    }

    return render_template('admin.html',
        clients=clients,
        selected_client=selected_client,
        files=files, messages=messages, payments=payments,
        stats=stats, unread_per_client=unread_per_client,
    )


@app.route('/admin/message/<int:client_id>', methods=['POST'])
@login_required
@admin_required
def admin_send_message(client_id):
    client = User.query.filter_by(id=client_id, role='client').first_or_404()
    content = request.form.get('content', '').strip()
    if content:
        db.session.add(Message(
            user_id=client_id,
            sender_role='admin',
            sender_name=current_user.name,
            content=content
        ))
        db.session.commit()
        notify_client(client.email, 'New message from Amber Consulting',
            f'Hi {client.name},\n\nYou have a new message from your consultant:\n\n{content}\n\nLog in to reply: {request.host_url}login')
    return redirect(url_for('admin', client_id=client_id) + '#messages')


@app.route('/admin/upload/<int:client_id>', methods=['POST'])
@login_required
@admin_required
def admin_upload_file(client_id):
    client = User.query.filter_by(id=client_id, role='client').first_or_404()
    if 'file' not in request.files or not request.files['file'].filename:
        flash('No file selected.', 'error')
        return redirect(url_for('admin', client_id=client_id) + '#files')

    f = request.files['file']
    if not allowed_file(f.filename):
        flash('File type not allowed.', 'error')
        return redirect(url_for('admin', client_id=client_id) + '#files')

    try:
        result = cloudinary.uploader.upload(
            f,
            resource_type='auto',
            folder=f'amber-consulting/{client_id}',
            use_filename=True,
            unique_filename=True
        )
        db.session.add(File(
            user_id=client_id,
            filename=f.filename,
            cloudinary_url=result['secure_url'],
            cloudinary_public_id=result['public_id']
        ))
        db.session.commit()
        notify_client(client.email, 'A file has been shared with you — Amber Consulting',
            f'Hi {client.name},\n\nYour consultant has shared a file with you: {f.filename}\n\nLog in to download it: {request.host_url}login')
        flash('File uploaded to client.', 'success')
    except Exception as e:
        app.logger.error('Upload failed: %s', e)
        flash('Upload failed. Please try again.', 'error')

    return redirect(url_for('admin', client_id=client_id) + '#files')


@app.route('/admin/invoice/<int:client_id>', methods=['POST'])
@login_required
@admin_required
def create_invoice(client_id):
    client = User.query.filter_by(id=client_id, role='client').first_or_404()
    amount = request.form.get('amount', type=float)
    description = request.form.get('description', '').strip()

    if not amount or amount <= 0:
        flash('Invalid amount.', 'error')
        return redirect(url_for('admin', client_id=client_id) + '#payments')

    db.session.add(Payment(user_id=client_id, amount=amount, description=description))
    db.session.commit()
    notify_client(client.email, 'New invoice from Amber Consulting',
        f'Hi {client.name},\n\nAn invoice has been created for you:\n\n{description or "Consulting Services"}: ${amount:,.2f}\n\nLog in to pay: {request.host_url}login')
    flash('Invoice created.', 'success')
    return redirect(url_for('admin', client_id=client_id) + '#payments')


@app.route('/admin/notes/<int:client_id>', methods=['POST'])
@login_required
@admin_required
def update_notes(client_id):
    client = User.query.filter_by(id=client_id, role='client').first_or_404()
    client.notes = request.form.get('notes', '').strip()
    db.session.commit()
    flash('Notes saved.', 'success')
    return redirect(url_for('admin', client_id=client_id))


@app.route('/admin/delete/<int:client_id>', methods=['POST'])
@login_required
@admin_required
def delete_client(client_id):
    client = User.query.filter_by(id=client_id, role='client').first_or_404()
    for f in client.files:
        try:
            cloudinary.uploader.destroy(f.cloudinary_public_id, resource_type='raw')
        except Exception as e:
            app.logger.warning('Cloudinary delete failed: %s', e)
    db.session.delete(client)
    db.session.commit()
    flash(f'{client.name} has been deleted.', 'success')
    return redirect(url_for('admin'))


@app.cli.command('reset-db')
def reset_db():
    db.drop_all()
    db.create_all()
    print('Database reset.')


if __name__ == '__main__':
    app.run(debug=True)
