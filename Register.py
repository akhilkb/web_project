"""Flask registration page for new users."""

from flask import Flask, render_template_string, request, redirect, url_for, flash
import uuid
from werkzeug.security import generate_password_hash

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

# HTML template
register_template = """

<!DOCTYPE html>
<html>
<head>
<title> Register Page </title>
<style>
 body {
 font-family : Arial, sans-serif;
 background: #f4f4f4;
 display:flex;
 justify-content:center;
 align-items:center;
 height:100vh;
 }

 .register-box{
 background: white;
 padding:30px;
 border-radius: 10px;
 width:350px;
 box-shadow: 0 0 10px rgba(0,0,0,0.1);
 }

 h2{
 text-align:center;
 margin-bottom:20px;
 }

 input{
 width:100%;
 padding: 10px;
 margin:8px 0;
 border:1px solid #ccc;
 border-radius :5px;
 box-sizing: border-box;
 }

 button {
 width:100%;
 padding:10px;
 background: #28a745;
 border:none;
 color:white;
 font-size:16px;
 border-radius:5px;
 cursor:pointer;
 }

 button:hover {
 background:#218838;
 }

 .messages {
 color:green;
 text-align:center;
 margin-bottom:10px;
 }

 .link {
 display:block;
 text-align:center;
 margin-top:12px;
 color:#007bff;
 text-decoration:none;
 }

 .secondary-button {
 background:#007bff;
 margin-top:8px;
 }

 .secondary-button:hover {
 background:#0056b3;
 }

 </style>
 </head>

 <body>
 <div class="register-box">
 <h2> Register </h2>
{% with messages = get_flashed_messages() %}
{% if messages %}
<div class="messages">{{ messages[0] }}</div>
{% endif %}
{% endwith %}

<form method="POST" onsubmit="return validateForm();">
<input type="text" name="username" id="username" placeholder="Username" required>
<input type="email" name="email" id="email" placeholder="Email" required>
<input type="password" name="password" id="password" placeholder="Password" required>
<button type="submit">Register</button>
</form>
<a class="link" href="/login">
<button type="button" class="secondary-button">Login</button>
</a>
<script>
function validateForm() {
  const username = document.getElementById('username').value.trim();
  const email = document.getElementById('email').value.trim();
  const password = document.getElementById('password').value;

  if (username.length < 3) {
    alert('Username must be at least 3 characters long.');
    return false;
  }

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
</div>
</body>
</html>
"""


@app.route('/register', methods=['GET', 'POST'])
def register():
    """
    Register a new user and save their data to DynamoDB.
    """
    if request.method == "POST":
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if len(username) < 3:
            flash("Username must be at least 3 characters long", "error")
            return redirect(url_for('register'))

        if '@' not in email or '.' not in email:
            flash("Please enter a valid email address", "error")
            return redirect(url_for('register'))

        if len(password) < 6:
            flash("Password must be at least 6 characters long", "error")
            return redirect(url_for('register'))

        if table is None:
            flash("Registration is temporarily unavailable because AWS services could not be loaded.", "error")
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)
        try:

            # Check if user exists using the table's real schema
            response = table.scan(FilterExpression=Attr('email').eq(email))
            if response['Items']:
                flash("Email already registered", "error")
                return redirect(url_for('register'))
            
            # Save user with the required primary key
            table.put_item(
                Item={
                    'user_id': str(uuid.uuid4()),
                    'email': email,
                    'username': username,
                    'password': hashed_password
                }
            )
            flash("Registration Successful")
            return redirect(url_for('login'))

        except ClientError as e:
            error_code = e.response['Error'].get('Code', 'Unknown')
            error_message = e.response['Error'].get('Message', str(e))
            flash(f"AWS Error [{error_code}]: {error_message}", "error")
            
        return redirect(url_for('login'))
    
    return render_template_string(register_template)

if __name__ == '__main__':
    app.run(debug=True)