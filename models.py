from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(10), default='client')  # 'client' or 'admin'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    files = db.relationship('File', backref='owner', lazy=True, cascade='all, delete-orphan')
    messages = db.relationship('Message', backref='user', lazy=True, cascade='all, delete-orphan')
    payments = db.relationship('Payment', backref='user', lazy=True, cascade='all, delete-orphan')


class File(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    filename = db.Column(db.String(256), nullable=False)
    cloudinary_url = db.Column(db.String(512), nullable=False)
    cloudinary_public_id = db.Column(db.String(256), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    sender_role = db.Column(db.String(10), nullable=False)  # 'client' or 'admin'
    sender_name = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(256))
    status = db.Column(db.String(20), default='pending')  # 'pending' or 'paid'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime, nullable=True)
