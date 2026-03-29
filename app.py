import os
from datetime import datetime
from functools import wraps

import cloudinary
import cloudinary.uploader
import resend

from flask import (
    Flask, render_template, request, jsonify,
    redirect, url_for, flash, abort
)
from flask_login import (
    LoginManager, login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

from models import db, User, File, Message, Payment

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')

DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///amber.db')
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'error'

resend.api_key = os.environ.get('RESEND_API_KEY', '')

cloudinary.config(
    cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME', ''),
    api_key=os.environ.get('CLOUDINARY_API_KEY', ''),
    api_secret=os.environ.get('CLOUDINARY_API_SECRET', '')
)

ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', '').lower()

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
        send_contact_email(name, email, message)
        return jsonify({'success': True})
    except KeyError as e:
        app.logger.error('Missing environment variable: %s', e)
        return jsonify({'success': False, 'error': 'Server misconfiguration. Please contact us directly.'}), 500
    except Exception as e:
        app.logger.error('Email send failed: %s', e)
        return jsonify({'success': False, 'error': 'Failed to send message. Please try again later.'}), 500


def send_contact_email(name, sender_email, message):
    recipient = os.environ['MAIL_RECIPIENT']
    resend.Emails.send({
        'from': 'Amber Consulting <onboarding@resend.dev>',
        'to': recipient,
        'subject': f'New contact form message from {name}',
        'text': f'Name: {name}\nEmail: {sender_email}\n\nMessage:\n{message}',
    })


# ── Auth routes ──

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('admin' if current_user.role == 'admin' else 'dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
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
        return redirect(url_for('admin' if role == 'admin' else 'dashboard'))

    return render_template('register.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


# ── Client dashboard ──

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'admin':
        return redirect(url_for('admin'))
    files = File.query.filter_by(user_id=current_user.id).order_by(File.uploaded_at.desc()).all()
    messages = Message.query.filter_by(user_id=current_user.id).order_by(Message.created_at.asc()).all()
    payments = Payment.query.filter_by(user_id=current_user.id).order_by(Payment.created_at.desc()).all()
    return render_template('dashboard.html', files=files, messages=messages, payments=payments)


@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files or not request.files['file'].filename:
        flash('No file selected.', 'error')
        return redirect(url_for('dashboard') + '#files')

    f = request.files['file']
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
        flash('File uploaded successfully.', 'success')
    except Exception as e:
        app.logger.error('Upload failed: %s', e)
        flash('Upload failed. Please try again.', 'error')

    return redirect(url_for('dashboard') + '#files')


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
            sender_role=current_user.role,
            sender_name=current_user.name,
            content=content
        ))
        db.session.commit()
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

    client_id = request.args.get('client_id', type=int)
    if client_id:
        selected_client = User.query.filter_by(id=client_id, role='client').first_or_404()
        files = File.query.filter_by(user_id=client_id).order_by(File.uploaded_at.desc()).all()
        messages = Message.query.filter_by(user_id=client_id).order_by(Message.created_at.asc()).all()
        payments = Payment.query.filter_by(user_id=client_id).order_by(Payment.created_at.desc()).all()

    return render_template('admin.html',
        clients=clients,
        selected_client=selected_client,
        files=files,
        messages=messages,
        payments=payments
    )


@app.route('/admin/message/<int:client_id>', methods=['POST'])
@login_required
@admin_required
def admin_send_message(client_id):
    User.query.filter_by(id=client_id, role='client').first_or_404()
    content = request.form.get('content', '').strip()
    if content:
        db.session.add(Message(
            user_id=client_id,
            sender_role='admin',
            sender_name=current_user.name,
            content=content
        ))
        db.session.commit()
    return redirect(url_for('admin', client_id=client_id) + '#messages')


@app.route('/admin/invoice/<int:client_id>', methods=['POST'])
@login_required
@admin_required
def create_invoice(client_id):
    User.query.filter_by(id=client_id, role='client').first_or_404()
    amount = request.form.get('amount', type=float)
    description = request.form.get('description', '').strip()

    if not amount or amount <= 0:
        flash('Invalid amount.', 'error')
        return redirect(url_for('admin', client_id=client_id) + '#payments')

    db.session.add(Payment(user_id=client_id, amount=amount, description=description))
    db.session.commit()
    flash('Invoice created.', 'success')
    return redirect(url_for('admin', client_id=client_id) + '#payments')


if __name__ == '__main__':
    app.run(debug=True)
