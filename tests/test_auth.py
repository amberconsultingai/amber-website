from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash
from models import db, User


def test_register_creates_client_user(client, app):
    res = client.post('/register', data={
        'name': 'Jane Doe',
        'email': 'jane@test.com',
        'password': 'securepass',
        'confirm_password': 'securepass',
    }, follow_redirects=True)
    assert res.status_code == 200
    with app.app_context():
        user = User.query.filter_by(email='jane@test.com').first()
        assert user is not None
        assert user.role == 'client'


def test_register_admin_email_gets_admin_role(client, app):
    # ADMIN_EMAIL is set to 'admin@test.com' in conftest
    res = client.post('/register', data={
        'name': 'Admin',
        'email': 'admin@test.com',
        'password': 'securepass',
        'confirm_password': 'securepass',
    }, follow_redirects=True)
    assert res.status_code == 200
    with app.app_context():
        user = User.query.filter_by(email='admin@test.com').first()
        assert user.role == 'admin'


def test_register_password_mismatch_shows_error(client):
    res = client.post('/register', data={
        'name': 'Jane',
        'email': 'jane@test.com',
        'password': 'password1',
        'confirm_password': 'password2',
    })
    assert b'do not match' in res.data


def test_register_short_password_rejected(client):
    res = client.post('/register', data={
        'name': 'Jane',
        'email': 'jane@test.com',
        'password': 'short',
        'confirm_password': 'short',
    })
    assert b'8 characters' in res.data


def test_register_duplicate_email_rejected(client, client_user):
    res = client.post('/register', data={
        'name': 'Other',
        'email': client_user['email'],
        'password': 'password123',
        'confirm_password': 'password123',
    })
    assert b'already exists' in res.data


def test_login_valid_credentials_redirects_to_dashboard(client, client_user):
    res = client.post('/login', data={
        'email': client_user['email'],
        'password': client_user['password'],
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b'Dashboard' in res.data or b'Files' in res.data


def test_login_invalid_password_shows_error(client, client_user):
    res = client.post('/login', data={
        'email': client_user['email'],
        'password': 'wrongpassword',
    })
    assert b'Invalid email or password' in res.data


def test_login_admin_redirects_to_admin_panel(client, admin_user):
    res = client.post('/login', data={
        'email': admin_user['email'],
        'password': admin_user['password'],
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b'Admin' in res.data or b'Clients' in res.data


def test_logout_redirects_to_index(logged_in_client):
    res = logged_in_client.get('/logout', follow_redirects=True)
    assert res.status_code == 200
    assert b'AMBR Consulting' in res.data


def test_forgot_password_sends_email(client, client_user, mocker, app):
    mock_send = mocker.patch('app.resend.Emails.send')
    res = client.post('/forgot-password', data={'email': client_user['email']}, follow_redirects=True)
    assert res.status_code == 200
    assert b'reset link has been sent' in res.data
    mock_send.assert_called_once()
    with app.app_context():
        user = User.query.filter_by(email=client_user['email']).first()
        assert user.reset_token is not None


def test_forgot_password_unknown_email_shows_no_hint(client, mocker):
    mocker.patch('app.resend.Emails.send')
    res = client.post('/forgot-password', data={'email': 'nobody@test.com'}, follow_redirects=True)
    # Should show same success message to prevent email enumeration
    assert b'reset link has been sent' in res.data


def test_reset_password_with_valid_token(client, client_user, app):
    with app.app_context():
        user = User.query.filter_by(email=client_user['email']).first()
        user.reset_token = 'valid-token-123'
        user.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
        db.session.commit()

    res = client.post('/reset-password/valid-token-123', data={
        'password': 'newpassword123',
        'confirm_password': 'newpassword123',
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b'Password updated' in res.data


def test_reset_password_expired_token_rejected(client, client_user, app):
    with app.app_context():
        user = User.query.filter_by(email=client_user['email']).first()
        user.reset_token = 'expired-token'
        user.reset_token_expires = datetime.utcnow() - timedelta(hours=2)
        db.session.commit()

    res = client.post('/reset-password/expired-token', data={
        'password': 'newpassword123',
        'confirm_password': 'newpassword123',
    }, follow_redirects=True)
    assert b'Invalid or expired' in res.data
