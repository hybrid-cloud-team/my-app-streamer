import os
import boto3
from flask import Flask, render_template_string, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "secret_key_for_session" # 보안을 위해 필수

# 환경 변수 설정
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
S3_BUCKET = os.getenv("S3_BUCKET")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# DB 연결
app.config['SQLALCHEMY_DATABASE_URI'] = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# 로그인 매니저 설정
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # 로그인 안 된 사용자가 접근하면 여기로 보냄

# S3 클라이언트
s3_client = boto3.client(
    's3',
    region_name=AWS_REGION,
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
)

# --- 모델 정의 (RDS 테이블) ---

# 사용자 모델 (새로 추가됨!)
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False) # 암호화된 비밀번호 저장

# 비디오 모델
class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    s3_key = db.Column(db.String(200), nullable=False)
    # 누가 올렸는지 기록 (선택 사항)
    uploader = db.Column(db.String(150), nullable=True)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- HTML 템플릿 (로그인/가입 UI 추가) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Hybrid Cloud Demo</title>
    <style>
        body { font-family: sans-serif; text-align: center; padding: 20px; background-color: #f4f4f4; }
        .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
        .nav { margin-bottom: 20px; padding: 10px; background: #eee; border-radius: 5px; }
        .nav a { margin: 0 10px; text-decoration: none; color: #333; font-weight: bold; }
        .video-box { margin: 20px; padding: 15px; border: 1px solid #ddd; border-radius: 8px; }
        input { padding: 10px; margin: 5px; width: 200px; }
        button { padding: 10px 20px; background-color: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; }
        button:hover { background-color: #0056b3; }
        .flash { color: green; font-weight: bold; }
        .error { color: red; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <div class="nav">
            <a href="/">🏠 Home</a>
            {% if current_user.is_authenticated %}
                <span>👤 {{ current_user.username }}</span>
                <a href="/logout">🚪 Logout</a>
            {% else %}
                <a href="/login">🔑 Login</a>
                <a href="/register">📝 Register</a>
            {% endif %}
        </div>

        <h1>🎬 Hybrid Cloud Streamer</h1>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <p class="{{ category }}">{{ message }}</p>
                {% endfor %}
            {% endif %}
        {% endwith %}

        {% block content %}{% endblock %}
    </div>
</body>
</html>
"""

# 홈 화면 (영상 목록)
@app.route('/')
def index():
    videos_db = Video.query.order_by(Video.id.desc()).all()
    videos_display = []
    
    for v in videos_db:
        try:
            url = s3_client.generate_presigned_url('get_object', Params={'Bucket': S3_BUCKET, 'Key': v.s3_key}, ExpiresIn=3600)
            videos_display.append({'title': v.title, 's3_key': v.s3_key, 'url': url, 'uploader': v.uploader})
        except: pass

    content = """
    {% if current_user.is_authenticated %}
        <div style="background: #e9ecef; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
            <h3>📤 Upload New Video</h3>
            <form action="/upload" method="post" enctype="multipart/form-data">
                <input type="text" name="title" placeholder="Video Title" required>
                <input type="file" name="file" accept="video/*" required>
                <button type="submit">Upload</button>
            </form>
        </div>
    {% else %}
        <p>🔒 <b>Login to upload videos.</b></p>
    {% endif %}
    
    <hr>
    {% for video in videos %}
        <div class="video-box">
            <h3>{{ video.title }}</h3>
            <video width="320" controls><source src="{{ video.url }}" type="video/mp4"></video>
            <p>Uploaded by: {{ video.uploader if video.uploader else 'Anonymous' }}</p>
        </div>
    {% endfor %}
    """
    return render_template_string(HTML_TEMPLATE.replace('{% block content %}{% endblock %}', content), videos=videos_display)

# 로그인 페이지
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash('Login Successful!', 'flash')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'error')

    content = """
    <h2>🔑 Login</h2>
    <form method="post">
        <input type="text" name="username" placeholder="Username" required><br>
        <input type="password" name="password" placeholder="Password" required><br>
        <button type="submit">Login</button>
    </form>
    """
    return render_template_string(HTML_TEMPLATE.replace('{% block content %}{% endblock %}', content))

# 회원가입 페이지
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
        else:
            # 비밀번호 암호화 저장 (보안 필수)
            hashed_pw = generate_password_hash(password)
            new_user = User(username=username, password=hashed_pw)
            db.session.add(new_user)
            db.session.commit()
            flash('Account created! Please login.', 'flash')
            return redirect(url_for('login'))

    content = """
    <h2>📝 Register</h2>
    <form method="post">
        <input type="text" name="username" placeholder="Username" required><br>
        <input type="password" name="password" placeholder="Password" required><br>
        <button type="submit">Sign Up</button>
    </form>
    """
    return render_template_string(HTML_TEMPLATE.replace('{% block content %}{% endblock %}', content))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out.', 'flash')
    return redirect(url_for('index'))

@app.route('/upload', methods=['POST'])
@login_required  # 로그인을 안 하면 업로드 불가!
def upload():
    title = request.form['title']
    file = request.files['file']
    if file:
        filename = secure_filename(file.filename)
        try:
            s3_client.upload_fileobj(file, S3_BUCKET, filename, ExtraArgs={'ContentType': file.content_type})
            # 업로더 정보도 같이 저장
            new_video = Video(title=title, s3_key=filename, uploader=current_user.username)
            db.session.add(new_video)
            db.session.commit()
            flash(f"Upload Success!", 'flash')
        except Exception as e:
            flash(f"Error: {str(e)}", 'error')
    return redirect(url_for('index'))

@app.route('/health')
def health(): return "OK", 200

if __name__ == '__main__':
    with app.app_context():
        db.create_all() # 여기서 User 테이블이 자동으로 생성됩니다.
    app.run(host='0.0.0.0', port=8080)