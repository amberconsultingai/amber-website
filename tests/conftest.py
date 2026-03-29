import os
import tempfile
import pytest

# Must be set before importing app so db.create_all() is skipped at module level
os.environ['FLASK_TESTING'] = '1'
os.environ.setdefault('SECRET_KEY', 'test-secret-key')
os.environ.setdefault('ADMIN_EMAIL', 'admin@test.com')
os.environ.setdefault('RESEND_API_KEY', 'fake-resend-key')
os.environ.setdefault('MAIL_RECIPIENT', 'notify@test.com')
os.environ.setdefault('CLOUDINARY_CLOUD_NAME', 'fake-cloud')
os.environ.setdefault('CLOUDINARY_API_KEY', 'fake-key')
os.environ.setdefault('CLOUDINARY_API_SECRET', 'fake-secret')

from app import app as flask_app
from models import db, User, Payment, Message, File
from werkzeug.security import generate_password_hash


@pytest.fixture
def app():
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    flask_app.config.update({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
        'RATELIMIT_ENABLED': False,
        'SECRET_KEY': 'test-secret-key',
    })

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()

    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def client_user(app):
    """Creates a client-role user and returns their credentials."""
    with app.app_context():
        user = User(
            email='client@test.com',
            name='Test Client',
            password_hash=generate_password_hash('password123'),
            role='client',
        )
        db.session.add(user)
        db.session.commit()
        return {'email': 'client@test.com', 'password': 'password123', 'id': user.id, 'name': user.name}


@pytest.fixture
def admin_user(app):
    """Creates an admin-role user and returns their credentials."""
    with app.app_context():
        user = User(
            email='admin@test.com',
            name='Admin User',
            password_hash=generate_password_hash('adminpass123'),
            role='admin',
        )
        db.session.add(user)
        db.session.commit()
        return {'email': 'admin@test.com', 'password': 'adminpass123', 'id': user.id, 'name': user.name}


@pytest.fixture
def logged_in_client(client, client_user):
    """Test client logged in as a regular client user."""
    client.post('/login', data={'email': client_user['email'], 'password': client_user['password']})
    return client


@pytest.fixture
def logged_in_admin(client, admin_user):
    """Test client logged in as an admin user."""
    client.post('/login', data={'email': admin_user['email'], 'password': admin_user['password']})
    return client
