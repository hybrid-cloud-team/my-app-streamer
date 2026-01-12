import os
import boto3
from flask import Flask, render_template_string, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "secret_key_for_session" # 플래시 메시지용

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

# S3 클라이언트
s3_client = boto3.client(
    's3',
    region_name=AWS_REGION,
    # 로컬 테스트용 (K8s에선 환경변수/IAM 사용)
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
)

# DB 모델
class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    s3_key = db.Column(db.String(200), nullable=False)

# HTML 템플릿 (홈 + 업로드 통합)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Hybrid Cloud Demo</title>
    <style>
        body { font-family: sans-serif; text-align: center; padding: 20px; }
        .container { max-width: 800px; margin: 0 auto; }
        .video-box { margin: 20px; padding: 15px; border: 1px solid #ddd; border-radius: 8px; display: inline-block; vertical-align: top; width: 320px; }
        .upload-box { background: #f9f9f9; padding: 20px; border-radius: 8px; margin-bottom: 30px; border: 2px dashed #ccc; }
        input, button { padding: 10px; margin: 5px; }
        button { background-color: #007bff; color: white; border: none; cursor: pointer; border-radius: 4px; }
        button:hover { background-color: #0056b3; }
        h1 { color: #333; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎬 Hybrid Cloud Streamer</h1>
        <p>Served from: <b>{{ pod_name }}</b> | Region: <b>{{ region }}</b></p>
        
        <div class="upload-box">
            <h3>📤 Upload New Video</h3>
            <form action="/upload" method="post" enctype="multipart/form-data">
                <input type="text" name="title" placeholder="Video Title" required style="width: 200px;">
                <input type="file" name="file" accept="video/*" required>
                <button type="submit">Upload to S3</button>
            </form>
            {% with messages = get_flashed_messages() %}
                {% if messages %}
                    <p style="color: green;">{{ messages[0] }}</p>
                {% endif %}
            {% endwith %}
        </div>

        <hr>

        <div class="video-list">
            {% for video in videos %}
                <div class="video-box">
                    <h4>{{ video.title }}</h4>
                    <video width="300" controls>
                        <source src="{{ video.url }}" type="video/mp4">
                        Your browser does not support the video tag.
                    </video>
                    <p style="font-size:12px; color:#666;">Key: {{ video.s3_key }}</p>
                </div>
            {% else %}
                <p>No videos found. Upload one!</p>
            {% endfor %}
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    # DB 조회
    videos_db = Video.query.order_by(Video.id.desc()).all()
    videos_display = []
    
    # Presigned URL 생성
    for v in videos_db:
        try:
            url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': S3_BUCKET, 'Key': v.s3_key},
                ExpiresIn=3600
            )
            videos_display.append({'title': v.title, 's3_key': v.s3_key, 'url': url})
        except Exception as e:
            print(f"Error generating URL for {v.title}: {e}")

    return render_template_string(HTML_TEMPLATE, videos=videos_display, 
                                  pod_name=os.getenv("HOSTNAME"), region=AWS_REGION)

@app.route('/upload', methods=['POST'])
def upload():
    title = request.form['title']
    file = request.files['file']

    if file:
        filename = secure_filename(file.filename)
        
        # 1. S3 업로드
        try:
            s3_client.upload_fileobj(
                file,
                S3_BUCKET,
                filename,
                ExtraArgs={'ContentType': file.content_type}
            )
            
            # 2. DB 저장
            new_video = Video(title=title, s3_key=filename)
            db.session.add(new_video)
            db.session.commit()
            
            flash(f"✅ Upload Success: {title}")
        except Exception as e:
            flash(f"❌ Error: {str(e)}")
            
    return redirect(url_for('index'))

@app.route('/health')
def health():
    return "OK", 200

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=8080)