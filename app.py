import os
import resend

from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
resend.api_key = os.environ["RESEND_API_KEY"]


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
    except Exception as e:
        app.logger.error("Email send failed: %s", e)
        return jsonify({"success": False, "error": "Failed to send message. Please try again later."}), 500


def send_email(name, sender_email, message):
    recipient = os.environ["MAIL_RECIPIENT"]

    resend.Emails.send({
        "from": "Amber Consulting <onboarding@resend.dev>",
        "to": recipient,
        "subject": f"New contact form message from {name}",
        "text": f"Name: {name}\nEmail: {sender_email}\n\nMessage:\n{message}",
    })


if __name__ == "__main__":
    app.run(debug=True)
