import io
from models import db, Payment, Message, File


def test_dashboard_requires_login(client):
    res = client.get('/dashboard', follow_redirects=True)
    assert b'log in' in res.data.lower()


def test_dashboard_loads_for_client(logged_in_client):
    res = logged_in_client.get('/dashboard')
    assert res.status_code == 200
    assert b'Files' in res.data


def test_admin_visiting_dashboard_redirects_to_admin(logged_in_admin):
    res = logged_in_admin.get('/dashboard', follow_redirects=True)
    assert res.status_code == 200
    assert b'Admin' in res.data or b'Clients' in res.data


def test_upload_invalid_file_type_rejected(logged_in_client):
    data = {'file': (io.BytesIO(b'bad content'), 'malware.exe')}
    res = logged_in_client.post('/upload', data=data,
                                content_type='multipart/form-data', follow_redirects=True)
    assert b'not allowed' in res.data


def test_upload_valid_file_succeeds(logged_in_client, mocker, app, client_user):
    mocker.patch('app.cloudinary.uploader.upload', return_value={
        'secure_url': 'https://res.cloudinary.com/fake/raw/upload/test.pdf',
        'public_id': 'amber-consulting/1/test_pdf',
    })
    mocker.patch('app.resend.Emails.send')

    data = {'file': (io.BytesIO(b'%PDF-1.4 content'), 'report.pdf')}
    res = logged_in_client.post('/upload', data=data,
                                content_type='multipart/form-data', follow_redirects=True)
    assert res.status_code == 200
    with app.app_context():
        f = File.query.filter_by(user_id=client_user['id']).first()
        assert f is not None
        assert f.filename == 'report.pdf'


def test_upload_notifies_admin(logged_in_client, mocker, client_user):
    mocker.patch('app.cloudinary.uploader.upload', return_value={
        'secure_url': 'https://res.cloudinary.com/fake/raw/upload/test.pdf',
        'public_id': 'amber-consulting/1/test_pdf',
    })
    mock_send = mocker.patch('app.resend.Emails.send')

    data = {'file': (io.BytesIO(b'content'), 'doc.pdf')}
    logged_in_client.post('/upload', data=data, content_type='multipart/form-data')
    mock_send.assert_called_once()
    call_args = mock_send.call_args[0][0]
    assert client_user['name'] in call_args['subject']


def test_send_message_saves_and_notifies_admin(logged_in_client, mocker, app, client_user):
    mock_send = mocker.patch('app.resend.Emails.send')
    res = logged_in_client.post('/messages/send', data={'content': 'Hello consultant!'}, follow_redirects=True)
    assert res.status_code == 200
    with app.app_context():
        msg = Message.query.filter_by(user_id=client_user['id']).first()
        assert msg is not None
        assert msg.content == 'Hello consultant!'
        assert msg.sender_role == 'client'
    mock_send.assert_called_once()


def test_send_empty_message_ignored(logged_in_client, app, client_user):
    logged_in_client.post('/messages/send', data={'content': '   '})
    with app.app_context():
        count = Message.query.filter_by(user_id=client_user['id']).count()
        assert count == 0


def test_make_payment_marks_paid(logged_in_client, app, client_user):
    with app.app_context():
        payment = Payment(user_id=client_user['id'], amount=500.00,
                          description='Strategy Session', status='pending')
        db.session.add(payment)
        db.session.commit()
        payment_id = payment.id

    res = logged_in_client.post(f'/payments/{payment_id}/pay', follow_redirects=True)
    assert res.status_code == 200
    with app.app_context():
        p = db.session.get(Payment, payment_id)
        assert p.status == 'paid'
        assert p.paid_at is not None


def test_download_requires_login(client, app, client_user):
    with app.app_context():
        f = File(user_id=client_user['id'], filename='test.pdf',
                 cloudinary_url='https://example.com/test.pdf',
                 cloudinary_public_id='amber-consulting/1/test_pdf')
        db.session.add(f)
        db.session.commit()
        file_id = f.id

    res = client.get(f'/download/{file_id}', follow_redirects=True)
    assert b'log in' in res.data.lower()


def test_client_cannot_download_other_users_file(logged_in_client, app):
    with app.app_context():
        from models import User
        from werkzeug.security import generate_password_hash
        other_user = User(email='other@test.com', name='Other',
                          password_hash=generate_password_hash('pass'), role='client')
        db.session.add(other_user)
        db.session.commit()
        f = File(user_id=other_user.id, filename='secret.pdf',
                 cloudinary_url='https://example.com/secret.pdf',
                 cloudinary_public_id='amber-consulting/99/secret')
        db.session.add(f)
        db.session.commit()
        file_id = f.id

    res = logged_in_client.get(f'/download/{file_id}')
    assert res.status_code == 404
