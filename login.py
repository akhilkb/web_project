"""Flask login page for user authentication."""

from flask import Flask, render_template_string, request, redirect, url_for, flash, session
from werkzeug.security import check_password_hash
import Register
import welcome as welcome_page

try:
    import boto3
    from boto3.dynamodb.conditions import Attr
    from botocore.exceptions import ClientError
except Exception as exc:
    boto3 = None
    Attr = None
    ClientError = Exception
    print(f"[AWS IMPORT ERROR] {exc}")

app = Flask(__name__)
app.secret_key = 'Ffe6dXyDaFb9eqVyHinxT04U9I9/80PDyS/roJLH'

# AWS DynamoDB setup
if boto3 is None:
    dynamodb = None
    table = None
else:
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    table = dynamodb.Table('users')

login_template = """
<!DOCTYPE html>
<html>
<head>
<title> Login Page </title>
<style>
 body {
 font-family: Arial, sans-serif;
 background: #f4f4f4;
 display:flex;
 justify-content:center;
 align-items:center;
 height:100vh;
 margin:0;
 }

 .login-box {
 background: white;
 padding:30px;
 border-radius: 10px;
 width:350px;
 box-shadow: 0 0 10px rgba(0,0,0,0.1);
 }

 h2 {
 text-align:center;
 margin-bottom:20px;
 }

 input {
 width:100%;
 padding:10px;
 margin:8px 0;
 border:1px solid #ccc;
 border-radius:5px;
 box-sizing:border-box;
 }

 button {
 width:100%;
 padding:10px;
 background:#007bff;
 border:none;
 color:white;
 font-size:16px;
 border-radius:5px;
 cursor:pointer;
 }

 button:hover {
 background:#0056b3;
 }

 .messages {
 text-align:center;
 margin-bottom:10px;
 }

 .error { color:red; }
 .success { color:green; }

 .link {
 display:block;
 text-align:center;
 margin-top:12px;
 color:#007bff;
 text-decoration:none;
 }
</style>
</head>
<body>
<div class="login-box">
  <h2>Login</h2>
  {% with messages = get_flashed_messages(with_categories=true) %}
    {% if messages %}
      {% for category, message in messages %}
        <div class="messages {{ category }}">{{ message }}</div>
      {% endfor %}
    {% endif %}
  {% endwith %}

  <form method="POST" onsubmit="return validateLoginForm();">
    <input type="email" name="email" id="email" placeholder="Email" required>
    <input type="password" name="password" id="password" placeholder="Password" required>
    <button type="submit">Login</button>
  </form>
  <script>
  function validateLoginForm() {
    const email = document.getElementById('email').value.trim();
    const password = document.getElementById('password').value;

    const emailPattern = /^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/;
    if (!emailPattern.test(email)) {
      alert('Please enter a valid email address.');
      return false;
    }

    if (password.length < 6) {
      alert('Password must be at least 6 characters long.');
      return false;
    }

    return true;
  }
  </script>
  <a class="link" href="{{ url_for('register') }}">
    <button type="button" style="background:#28a745; width:100%; margin-top:8px;">Register</button>
  </a>
</div>
</body>
</html>
"""


@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    """
    Authenticate a user and redirect them to the welcome page.
    """
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if table is None:
            flash('Authentication is unavailable because AWS services could not be loaded.', 'error')
            return redirect(url_for('login'))

        try:
            response = table.scan(FilterExpression=Attr('email').eq(email))
            user = response.get('Items', [None])[0]

            if not user or not check_password_hash(user.get('password', ''), password):
                print(f"[LOGIN FAILED] {email} tried to log in")
                flash('Invalid email or password', 'error')
                return redirect(url_for('login'))

            username = user.get('username', 'User')
            session.clear()
            session['logged_in'] = True
            session['username'] = username
            session['email'] = email
            print(f"[LOGIN] {email} logged in as {username}")
            return redirect(url_for('welcome', username=username, email=email))

        except ClientError as e:
            error_code = e.response['Error'].get('Code', 'Unknown')
            error_message = e.response['Error'].get('Message', str(e))
            flash(f'AWS Error [{error_code}]: {error_message}', 'error')
            return redirect(url_for('login'))

    return render_template_string(login_template)


app.add_url_rule('/register', endpoint='register', view_func=Register.register, methods=['GET', 'POST'])
app.add_url_rule('/welcome', endpoint='welcome', view_func=welcome_page.app.view_functions['welcome'], methods=['GET', 'POST'])
app.add_url_rule('/resume_result', endpoint='resume_result', view_func=welcome_page.app.view_functions['resume_result'], methods=['GET'])


@app.route('/logout')
def logout():
    """Clear the current user session and return to the login page."""
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True)
