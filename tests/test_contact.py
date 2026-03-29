def test_contact_form_success(client, mocker):
    mocker.patch('app.resend.Emails.send')
    res = client.post('/contact', data={
        'name': 'Jane Doe',
        'email': 'jane@test.com',
        'message': 'Hello, I would like to learn more.',
    })
    assert res.status_code == 200
    assert res.get_json()['success'] is True


def test_contact_form_missing_fields_returns_400(client):
    res = client.post('/contact', data={'name': 'Jane'})
    assert res.status_code == 400
    assert res.get_json()['success'] is False


def test_contact_form_calls_resend_with_correct_recipient(client, mocker):
    mock_send = mocker.patch('app.resend.Emails.send')
    client.post('/contact', data={
        'name': 'Jane',
        'email': 'jane@test.com',
        'message': 'Test message',
    })
    call_args = mock_send.call_args[0][0]
    assert call_args['to'] == 'notify@test.com'
    assert 'Jane' in call_args['subject']


def test_contact_form_email_failure_returns_500(client, mocker):
    mocker.patch('app.resend.Emails.send', side_effect=Exception('Send failed'))
    res = client.post('/contact', data={
        'name': 'Jane',
        'email': 'jane@test.com',
        'message': 'Test message',
    })
    assert res.status_code == 500
    assert res.get_json()['success'] is False
