import os
import boto3
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-this-in-production") # 환경 변수에서 가져오기
# 파일 업로드 크기 제한 설정 (2GB로 설정, 0은 무제한)
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 * 1024  # 2GB

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

# 첫 화면 - 로그인 안 된 경우 로그인 페이지로 리다이렉트
@app.route('/')
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    
    # 로그인된 경우 동영상 목록 표시
    videos_db = Video.query.order_by(Video.id.desc()).all()
    videos_display = []
    
    for v in videos_db:
        try:
            url = s3_client.generate_presigned_url('get_object', Params={'Bucket': S3_BUCKET, 'Key': v.s3_key}, ExpiresIn=3600)
            videos_display.append({'id': v.id, 'title': v.title, 's3_key': v.s3_key, 'url': url, 'uploader': v.uploader})
        except Exception as e:
            print(f"Error generating URL for video {v.id}: {e}")
            pass
    
    return render_template('index.html', videos=videos_display)

# 로그인 페이지
@app.route('/login', methods=['GET', 'POST'])
def login():
    # 이미 로그인된 경우 메인 페이지로 리다이렉트
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash('로그인 성공!', 'flash')
            return redirect(url_for('index'))
        else:
            flash('사용자 이름 또는 비밀번호가 올바르지 않습니다.', 'error')

    return render_template('login.html')

# 회원가입 페이지
@app.route('/register', methods=['GET', 'POST'])
def register():
    # 이미 로그인된 경우 메인 페이지로 리다이렉트
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if User.query.filter_by(username=username).first():
            flash('이미 존재하는 사용자 이름입니다.', 'error')
        else:
            # 비밀번호 암호화 저장 (보안 필수)
            hashed_pw = generate_password_hash(password)
            new_user = User(username=username, password=hashed_pw)
            db.session.add(new_user)
            db.session.commit()
            flash('계정이 생성되었습니다! 로그인해주세요.', 'flash')
            return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('로그아웃되었습니다.', 'flash')
    return redirect(url_for('login'))

# 업로드 페이지 (GET) 및 업로드 처리 (POST)
@app.route('/upload', methods=['GET', 'POST'])
@login_required  # 로그인을 안 하면 업로드 불가!
def upload():
    if request.method == 'POST':
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
                flash('업로드 성공!', 'flash')
                return redirect(url_for('index'))
            except Exception as e:
                flash(f'업로드 오류: {str(e)}', 'error')
        else:
            flash('파일을 선택해주세요.', 'error')
    
    # GET 요청 시 업로드 페이지 표시
    return render_template('upload.html')

# 동영상 삭제
@app.route('/delete/<int:video_id>', methods=['POST'])
@login_required
def delete_video(video_id):
    video = Video.query.get_or_404(video_id)
    
    try:
        # 데이터베이스에서만 삭제 (S3 파일은 삭제하지 않음)
        # 모든 로그인한 사용자가 삭제 가능
        db.session.delete(video)
        db.session.commit()
        # AJAX 요청인 경우 JSON 응답
        if request.headers.get('Accept') and 'application/json' in request.headers.get('Accept', ''):
            return jsonify({'success': True, 'message': '동영상이 삭제되었습니다.'}), 200
        flash('동영상이 삭제되었습니다.', 'flash')
    except Exception as e:
        # AJAX 요청인 경우 JSON 응답
        if request.headers.get('Accept') and 'application/json' in request.headers.get('Accept', ''):
            return jsonify({'success': False, 'message': f'삭제 오류: {str(e)}'}), 500
        flash(f'삭제 오류: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(url_for('index'))

@app.route('/health')
def health(): return "OK", 200

# 데이터베이스 테이블 초기화 (앱 시작 시 한 번만 실행)
def init_db():
    with app.app_context():
        db.create_all()

if __name__ == '__main__':
    # 개발 환경에서만 직접 실행
    init_db()
    app.run(host='0.0.0.0', port=8080, debug=False)