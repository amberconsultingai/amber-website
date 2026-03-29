import io
from models import db, User, Payment, Message, File
from werkzeug.security import generate_password_hash


def test_admin_requires_login(client):
    res = client.get('/admin', follow_redirects=True)
    assert b'log in' in res.data.lower()


def test_client_cannot_access_admin(logged_in_client):
    res = logged_in_client.get('/admin')
    assert res.status_code == 403


def test_admin_overview_loads(logged_in_admin):
    res = logged_in_admin.get('/admin')
    assert res.status_code == 200
    assert b'Overview' in res.data


def test_admin_overview_shows_client_count(logged_in_admin, app, client_user):
    res = logged_in_admin.get('/admin')
    assert b'1' in res.data  # 1 client exists


def test_admin_can_view_client_detail(logged_in_admin, client_user):
    res = logged_in_admin.get(f'/admin?client_id={client_user["id"]}')
    assert res.status_code == 200
    assert client_user['name'].encode() in res.data


def test_admin_send_message_notifies_client(logged_in_admin, client_user, mocker, app):
    mock_send = mocker.patch('app.resend.Emails.send')
    res = logged_in_admin.post(f'/admin/message/{client_user["id"]}',
                               data={'content': 'Your report is ready.'},
                               follow_redirects=True)
    assert res.status_code == 200
    with app.app_context():
        msg = Message.query.filter_by(user_id=client_user['id']).first()
        assert msg is not None
        assert msg.sender_role == 'admin'
        assert msg.content == 'Your report is ready.'
    mock_send.assert_called_once()
    call_args = mock_send.call_args[0][0]
    assert call_args['to'] == client_user['email']


def test_create_invoice_notifies_client(logged_in_admin, client_user, mocker, app):
    mock_send = mocker.patch('app.resend.Emails.send')
    res = logged_in_admin.post(f'/admin/invoice/{client_user["id"]}',
                               data={'amount': '750.00', 'description': 'Q1 Planning'},
                               follow_redirects=True)
    assert res.status_code == 200
    with app.app_context():
        p = Payment.query.filter_by(user_id=client_user['id']).first()
        assert p is not None
        assert p.amount == 750.00
        assert p.status == 'pending'
    mock_send.assert_called_once()


def test_create_invoice_invalid_amount_rejected(logged_in_admin, client_user):
    res = logged_in_admin.post(f'/admin/invoice/{client_user["id"]}',
                               data={'amount': '-50', 'description': 'Bad'},
                               follow_redirects=True)
    assert b'Invalid amount' in res.data


def test_admin_upload_file_to_client(logged_in_admin, client_user, mocker, app):
    mocker.patch('app.cloudinary.uploader.upload', return_value={
        'secure_url': 'https://res.cloudinary.com/fake/raw/upload/report.pdf',
        'public_id': 'amber-consulting/1/report_pdf',
    })
    mocker.patch('app.resend.Emails.send')

    data = {'file': (io.BytesIO(b'report content'), 'q1_report.pdf')}
    res = logged_in_admin.post(f'/admin/upload/{client_user["id"]}',
                               data=data, content_type='multipart/form-data',
                               follow_redirects=True)
    assert res.status_code == 200
    with app.app_context():
        f = File.query.filter_by(user_id=client_user['id']).first()
        assert f is not None
        assert f.filename == 'q1_report.pdf'


def test_admin_save_notes(logged_in_admin, client_user, app):
    res = logged_in_admin.post(f'/admin/notes/{client_user["id"]}',
                               data={'notes': 'High-value client. Prefers email.'},
                               follow_redirects=True)
    assert res.status_code == 200
    with app.app_context():
        user = db.session.get(User, client_user['id'])
        assert user.notes == 'High-value client. Prefers email.'


def test_delete_client_removes_user_and_files(logged_in_admin, client_user, mocker, app):
    mocker.patch('app.cloudinary.uploader.destroy')
    with app.app_context():
        f = File(user_id=client_user['id'], filename='doc.pdf',
                 cloudinary_url='https://example.com/doc.pdf',
                 cloudinary_public_id='amber-consulting/1/doc')
        db.session.add(f)
        db.session.commit()

    res = logged_in_admin.post(f'/admin/delete/{client_user["id"]}', follow_redirects=True)
    assert res.status_code == 200
    with app.app_context():
        assert db.session.get(User, client_user['id']) is None
        assert File.query.filter_by(user_id=client_user['id']).count() == 0


def test_messages_marked_read_when_admin_views_client(logged_in_admin, client_user, app):
    with app.app_context():
        msg = Message(user_id=client_user['id'], sender_role='client',
                      sender_name='Test Client', content='Hello!', is_read=False)
        db.session.add(msg)
        db.session.commit()

    logged_in_admin.get(f'/admin?client_id={client_user["id"]}')

    with app.app_context():
        msg = Message.query.filter_by(user_id=client_user['id']).first()
        assert msg.is_read is True
