import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/contact", methods=["POST"])
def contact():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    message = request.form.get("message", "").strip()

    if not name or not email or not message:
        return jsonify({"success": False, "error": "All fields are required."}), 400

    try:
        send_email(name, email, message)
        return jsonify({"success": True})
    except KeyError as e:
        app.logger.error("Missing environment variable: %s", e)
        return jsonify({"success": False, "error": "Server misconfiguration. Please contact us directly."}), 500
    except Exception as e:
        app.logger.error("Email send failed: %s", e)
        return jsonify({"success": False, "error": "Failed to send message. Please try again later."}), 500


def send_email(name, sender_email, message):
    username = os.environ["MAIL_USERNAME"]
    password = os.environ["MAIL_PASSWORD"]
    recipient = os.environ["MAIL_RECIPIENT"]

    msg = MIMEMultipart()
    msg["From"] = username
    msg["To"] = recipient
    msg["Subject"] = f"New contact form message from {name}"

    body = f"Name: {name}\nEmail: {sender_email}\n\nMessage:\n{message}"
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(username, password)
        server.sendmail(username, recipient, msg.as_string())


if __name__ == "__main__":
    app.run(debug=True)
