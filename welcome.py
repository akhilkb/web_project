"""Flask app for resume upload and skill extraction."""

from flask import Flask, render_template_string, request, redirect, url_for, flash, session
import os
import base64
import uuid
import datetime
import re
import boto3
import spacy
from botocore.exceptions import ClientError
from docx import Document
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
import numpy as np

app = Flask(__name__)
app.secret_key = 'Ffe6dXyDaFb9eqVyHinxT04U9I9/80PDyS/roJLH'

# AWS DynamoDB setup
_dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
_RESUMES_TABLE_NAME = 'resumes'
_SKILLS_TABLE_NAME = 'skills'
_ALLOWED_EXTENSIONS = {'.pdf', '.docx'}
_MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
_JOB_CATALOG = [
    {'title': 'Python Developer', 'description': 'backend development using python flask django api services and data workflows.', 'skills': ['python', 'flask', 'django', 'api', 'backend']},
    {'title': 'Cloud Engineer', 'description': 'cloud infrastructure automation deployment aws docker kubernetes and devops operations.', 'skills': ['aws', 'docker', 'kubernetes', 'devops', 'cloud']},
    {'title': 'Data Analyst', 'description': 'sql data analysis dashboards reporting and business intelligence using data tools.', 'skills': ['sql', 'data analysis', 'power bi', 'tableau', 'analytics']},
    {'title': 'Frontend Developer', 'description': 'react javascript typescript html css user interface and web applications.', 'skills': ['react', 'javascript', 'typescript', 'html', 'css']},
    {'title': 'AI / ML Engineer', 'description': 'machine learning ai model building data science and predictive analytics.', 'skills': ['machine learning', 'ai', 'python', 'data science']},
]
_JOB_MATCHING_OPTIONS = {
    'balanced': 'Balanced',
    'strict': 'Strict',
    'advanced': 'Advanced'
}
_SKILL_KEYWORDS = [
    'python', 'flask', 'django', 'java', 'javascript', 'typescript', 'html', 'css',
    'react', 'node.js', 'node', 'sql', 'mysql', 'postgresql', 'mongodb', 'aws',
    'azure', 'docker', 'kubernetes', 'git', 'github', 'rest api', 'api', 'machine learning',
    'ai', 'data analysis', 'testing', 'pytest', 'c++', 'c#', 'php', 'bootstrap',
    'linux', 'bash', 'selenium', 'dynamodb', 'boto3', 'power bi', 'tableau'
]

try:
    _NLP = spacy.load('en_core_web_sm')
except OSError:
    _NLP = None


def ensure_resumes_table():
    """
    Create the resumes table if it does not exist yet.
    """
    client = boto3.client('dynamodb', region_name='us-east-1')
    try:
        client.describe_table(TableName=_RESUMES_TABLE_NAME)
        return _dynamodb.Table(_RESUMES_TABLE_NAME)
    except client.exceptions.ResourceNotFoundException:
        client.create_table(
            TableName=_RESUMES_TABLE_NAME,
            AttributeDefinitions=[{'AttributeName': 'resume_id', 'AttributeType': 'S'}],
            KeySchema=[{'AttributeName': 'resume_id', 'KeyType': 'HASH'}],
            BillingMode='PAY_PER_REQUEST'
        )
        waiter = client.get_waiter('table_exists')
        waiter.wait(TableName=_RESUMES_TABLE_NAME)
        return _dynamodb.Table(_RESUMES_TABLE_NAME)


def extract_text_from_resume(file_path, ext):
    """
    Extract plain text from a PDF or DOCX resume file.
    """
    try:
        if ext == '.pdf':
            reader = PdfReader(file_path)
            return '\n'.join(page.extract_text() or '' for page in reader.pages)
        if ext == '.docx':
            doc = Document(file_path)
            return '\n'.join(paragraph.text for paragraph in doc.paragraphs)
    except Exception as exc:
        print(f'[RESUME TEXT ERROR] {exc}')
    return ''


def extract_skills(resume_text):
    """
    Use NLP to extract likely skills from the resume text.
    """
    text = (resume_text or '').lower()
    if not text:
        return []

    found = set()

    if _NLP is not None:
        doc = _NLP(resume_text)
        for chunk in doc.noun_chunks:
            phrase = chunk.text.strip().lower()
            if len(phrase.split()) <= 3 and any(skill in phrase for skill in _SKILL_KEYWORDS):
                found.add(phrase)

        for token in doc:
            lemma = token.lemma_.lower().strip()
            if lemma in _SKILL_KEYWORDS:
                found.add(lemma)
            if token.text.lower().strip() in _SKILL_KEYWORDS:
                found.add(token.text.lower().strip())

    # Fallback: simple keyword search if NLP model is unavailable or returns no results.
    if not found:
        clean_text = re.sub(r'[^a-zA-Z0-9+#.\-/\s]', ' ', text)
        for skill in _SKILL_KEYWORDS:
            if re.search(r'\b' + re.escape(skill.lower()) + r'\b', clean_text):
                found.add(skill)

    return sorted(found, key=lambda item: (_SKILL_KEYWORDS.index(item) if item in _SKILL_KEYWORDS else len(_SKILL_KEYWORDS), item))


def ensure_skills_table():
    """Create the skills table if it does not exist yet."""
    client = boto3.client('dynamodb', region_name='us-east-1')
    try:
        client.describe_table(TableName=_SKILLS_TABLE_NAME)
        return _dynamodb.Table(_SKILLS_TABLE_NAME)
    except client.exceptions.ResourceNotFoundException:
        client.create_table(
            TableName=_SKILLS_TABLE_NAME,
            AttributeDefinitions=[{'AttributeName': 'user_email', 'AttributeType': 'S'}],
            KeySchema=[{'AttributeName': 'user_email', 'KeyType': 'HASH'}],
            BillingMode='PAY_PER_REQUEST'
        )
        waiter = client.get_waiter('table_exists')
        waiter.wait(TableName=_SKILLS_TABLE_NAME)
        return _dynamodb.Table(_SKILLS_TABLE_NAME)


def get_resume_record(resume_id):
    """
    Fetch a saved resume item from DynamoDB using its resume_id.
    """
    try:
        return _dynamodb.Table(_RESUMES_TABLE_NAME).get_item(Key={'resume_id': resume_id}).get('Item')
    except ClientError as exc:
        print(f'[RESUME FETCH ERROR] {exc}')
        return None


def calculate_resume_score(skills, text):
    """
    Return a simple 0-100 resume score based on extracted skills and text quality.
    """
    score = 0
    score += min(40, len(skills) * 5)
    if text and len(text.split()) >= 80:
        score += 20
    if text and len(text.split()) >= 150:
        score += 20
    if any(skill in skills for skill in ['python', 'aws', 'sql', 'flask', 'django', 'docker']):
        score += 15
    if len(skills) >= 5:
        score += 5
    return min(100, score)


try:
    _EMBEDDING_MODEL = SentenceTransformer('all-MiniLM-L6-v2')
except Exception as exc:
    print(f'[EMBEDDING MODEL ERROR] {exc}')
    _EMBEDDING_MODEL = None


def match_jobs_with_ml(skills):
    """Rank job roles using sentence-transformers embeddings and cosine similarity."""
    resume_text = ' '.join(skill.lower() for skill in skills if skill) if skills else 'software developer engineer'
    job_profiles = [
        ' '.join([item['title'], item['description'], ' '.join(item['skills'])])
        for item in _JOB_CATALOG
    ]

    if _EMBEDDING_MODEL is None:
        return []

    resume_vector = _EMBEDDING_MODEL.encode([resume_text], convert_to_numpy=True)
    job_vectors = _EMBEDDING_MODEL.encode(job_profiles, convert_to_numpy=True)
    similarities = np.dot(job_vectors, resume_vector.T).reshape(-1)
    ranked = sorted(zip(_JOB_CATALOG, similarities), key=lambda item: item[1], reverse=True)
    return ranked


def recommend_job(skills, algorithm='balanced'):
    """Suggest a job role using the ML-based matcher and keep the algorithm selector for compatibility."""
    ranked_jobs = match_jobs_with_ml(skills)
    if not ranked_jobs:
        return 'Software Developer'

    best_role, best_score = ranked_jobs[0]
    if best_score < 0.05:
        return 'Software Developer'

    if algorithm == 'strict' and best_score < 0.15:
        return 'Software Developer'

    return best_role['title']


welcome_template = """
<!DOCTYPE html>
<html>
<head>
<title>Welcome</title>
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
  .box {
    background:white;
    padding:30px;
    border-radius:10px;
    width:380px;
    text-align:center;
    box-shadow: 0 0 10px rgba(0,0,0,0.1);
  }
  h2 { margin-bottom:10px; }
  p { color:#555; }
  form { margin-top:15px; text-align:left; }
  input[type="file"] { width:100%; margin:8px 0; }
  button {
    width:100%;
    padding:10px;
    background:#007bff;
    border:none;
    color:white;
    border-radius:5px;
    cursor:pointer;
  }
  button:hover { background:#0056b3; }
  .msg { color:green; font-size:14px; margin-top:8px; }
  .logout-btn {
    display:inline-block;
    margin-top:15px;
    padding:10px 15px;
    background:#dc3545;
    color:white;
    text-decoration:none;
    border-radius:5px;
    font-size:14px;
  }
  .logout-btn:hover { background:#c82333; }
</style>
</head>
<body>
  <div class="box">
    <h2>Welcome, {{ username }}</h2>
    <p>You have successfully logged in.</p>

    <form method="POST" enctype="multipart/form-data">
      <label for="resume">Upload Resume (PDF/DOCX)</label>
      <input type="file" id="resume" name="resume" accept=".pdf,.docx" required>
      <label for="matching_algorithm" style="display:block; margin-top:10px;">Job Matching Algorithm</label>
      <select id="matching_algorithm" name="matching_algorithm" style="width:100%; padding:10px; margin:8px 0; border:1px solid #ccc; border-radius:5px;">
        <option value="balanced">Balanced</option>
        <option value="strict">Strict</option>
        <option value="advanced">Advanced</option>
      </select>
      <button type="submit">Upload Resume</button>
    </form>

    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for category, message in messages %}
          <p class="msg {{ category }}">{{ message }}</p>
        {% endfor %}
      {% endif %}
    {% endwith %}

    <a class="logout-btn" href="{{ url_for('logout') }}">Logout</a>
  </div>
</body>
</html>
"""

resume_result_template = """
<!DOCTYPE html>
<html>
<head>
<title>Resume Result</title>
<style>
  body { font-family: Arial, sans-serif; background: #f4f4f4; display:flex; justify-content:center; align-items:center; min-height:100vh; margin:0; }
  .box { background:white; padding:30px; border-radius:10px; width:420px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
  h2 { margin-bottom:8px; }
  p { color:#555; }
  .btn { display:block; width:100%; margin-top:12px; padding:10px; background:#007bff; color:white; text-decoration:none; text-align:center; border-radius:5px; }
  .btn:hover { background:#0056b3; }
  .skills { margin-top:14px; padding:10px; background:#f8f9fa; border-radius:6px; }
  .skill-chip { display:inline-block; margin:4px; padding:6px 8px; background:#e9f5ff; border-radius:999px; font-size:13px; }
</style>
</head>
<body>
  <div class="box">
    <h2>Resume Uploaded</h2>
    <p>File: {{ filename }}</p>
    <p>Uploaded by: {{ username }}</p>
    <p>Matching Algorithm: {{ matching_algorithm_label }}</p>
    <a class="btn" href="{{ url_for('resume_result', resume_id=resume_id, username=username, show_skills=1) }}">Extract Skills</a>
    <a class="btn" href="{{ url_for('resume_result', resume_id=resume_id, username=username, show_score=1) }}">Resume Score</a>
    <a class="btn" href="{{ url_for('resume_result', resume_id=resume_id, username=username, show_score=1, show_recommendation=1) }}">Job Recommendation</a>
    <a class="btn" style="background:#6c757d;" href="{{ url_for('welcome', username=username) }}">Back to Welcome</a>

    {% if skills %}
      <div class="skills">
        <strong>Detected Skills:</strong><br>
        {% for skill in skills %}
          <span class="skill-chip">{{ skill }}</span>
        {% endfor %}
      </div>
    {% elif show_skills %}
      <p>No skills were detected in this resume.</p>
    {% endif %}

    {% if show_score %}
      <div class="skills">
        <strong>Resume Score:</strong> {{ score }}/100
      </div>
    {% endif %}

    {% if show_recommendation %}
      <div class="skills">
        <strong>Recommended Job:</strong> {{ recommendation }}
      </div>
    {% endif %}
  </div>
</body>
</html>
"""

@app.route('/resume_result', methods=['GET'])
def resume_result():
    """
    Show the uploaded resume details and allow skill extraction on demand.
    """
    resume_id = request.args.get('resume_id', '')
    if not session.get('logged_in'):
        flash('Please login first to view the resume result.', 'error')
        return redirect(url_for('login'))

    username = session.get('username', request.args.get('username', 'User'))
    show_skills = request.args.get('show_skills', '0') == '1'
    show_score = request.args.get('show_score', '0') == '1'
    show_recommendation = request.args.get('show_recommendation', '0') == '1'

    if not resume_id:
        flash('Resume information is missing.', 'error')
        return redirect(url_for('welcome', username=username))

    resume_item = get_resume_record(resume_id)
    if not resume_item:
        flash('Resume could not be found.', 'error')
        return redirect(url_for('welcome', username=username))

    skills = resume_item.get('skills', []) if show_skills or show_score or show_recommendation else []
    text = resume_item.get('filename', '')
    score = calculate_resume_score(skills, text) if (show_score or show_recommendation) else None
    matching_algorithm = resume_item.get('matching_algorithm', 'balanced')
    recommendation = recommend_job(skills, matching_algorithm) if show_recommendation else None
    return render_template_string(
        resume_result_template,
        filename=resume_item.get('filename', 'Resume'),
        username=username,
        resume_id=resume_id,
        skills=skills,
        show_skills=show_skills,
        show_score=show_score,
        show_recommendation=show_recommendation,
        score=score,
        recommendation=recommendation,
        matching_algorithm_label=matching_algorithm.title(),
    )


@app.route('/welcome', methods=['GET', 'POST'])
def welcome():
    """
    Render the welcome page and handle resume uploads.
    """
    if not session.get('logged_in'):
        flash('Please login first to access the home page.', 'error')
        return redirect(url_for('login'))

    username = session.get('username', request.args.get('username', 'User'))
    user_email = session.get('email', request.args.get('email', 'unknown@example.com')).strip().lower()

    if request.method == 'POST':
        print(f"[UPLOAD] {username} started resume upload")
        matching_algorithm = request.form.get('matching_algorithm', 'balanced').strip().lower()
        file = request.files.get('resume')
        if not file or file.filename == '':
            flash('Please choose a resume file.', 'error')
            return redirect(url_for('welcome', username=username))

        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in _ALLOWED_EXTENSIONS:
            flash('Only PDF or DOCX files are allowed.', 'error')
            return redirect(url_for('welcome', username=username))

        file.stream.seek(0, os.SEEK_END)
        file_size = file.stream.tell()
        file.stream.seek(0)
        if file_size == 0:
            flash('The selected resume is empty.', 'error')
            return redirect(url_for('welcome', username=username))
        if file_size > _MAX_FILE_SIZE:
            flash('Resume file size must be 5 MB or less.', 'error')
            return redirect(url_for('welcome', username=username))

        upload_folder = os.path.join(os.getcwd(), 'uploads')
        os.makedirs(upload_folder, exist_ok=True)
        file_path = os.path.join(upload_folder, file.filename)
        file.save(file_path)

        try:
            resume_table = ensure_resumes_table()
            skills_table = ensure_skills_table()
            file.seek(0)
            file_content = file.read()
            extracted_text = extract_text_from_resume(file_path, ext)
            extracted_skills = extract_skills(extracted_text)
            resume_id = str(uuid.uuid4())
            resume_table.put_item(Item={
                'resume_id': resume_id,
                'username': username,
                'filename': file.filename,
                'file_path': file_path,
                'file_size': os.path.getsize(file_path),
                'content_type': file.mimetype or 'application/octet-stream',
                'content_base64': base64.b64encode(file_content).decode('utf-8'),
                'skills': extracted_skills,
                'matching_algorithm': matching_algorithm,
                'uploaded_at': datetime.datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'
            })
            skills_table.put_item(Item={
                'user_email': user_email,
                'username': username,
                'skills': extracted_skills,
                'updated_at': datetime.datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'
            })
            print(f"[UPLOAD SUCCESS] {username} uploaded {file.filename} to {file_path} and extracted skills: {', '.join(extracted_skills) if extracted_skills else 'none'}")
            flash('Resume uploaded successfully and saved to DynamoDB.', 'success')
            return redirect(url_for('resume_result', resume_id=resume_id, username=username))
        except ClientError as e:
            error_code = e.response['Error'].get('Code', 'Unknown')
            error_message = e.response['Error'].get('Message', str(e))
            print(f"[UPLOAD ERROR] {username} failed to save resume to DynamoDB: {error_code} - {error_message}")
            flash(f'DynamoDB Error [{error_code}]: {error_message}', 'error')

        return redirect(url_for('welcome', username=username))

    return render_template_string(welcome_template, username=username)


if __name__ == '__main__':
    app.run(debug=True)
