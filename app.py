import os
import boto3
from flask import Flask, render_template_string
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# 환경 변수 설정 (K8s Secret에서 주입)
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
S3_BUCKET = os.getenv("S3_BUCKET")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# DB 연결 설정
app.config['SQLALCHEMY_DATABASE_URI'] = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# S3 클라이언트 설정
s3_client = boto3.client('s3', region_name=AWS_REGION)

# DB 모델 (영상 정보)
class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    s3_key = db.Column(db.String(200), nullable=False) # S3 내 파일 경로

# HTML 템플릿 (간단한 UI)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head><title>Hybrid Cloud Demo</title></head>
<body style="text-align:center; font-family:sans-serif;">
    <h1>🎬 Hybrid Cloud Video Streamer</h1>
    <p>Served from Pod: <b>{{ pod_name }}</b></p>
    <hr>
    {% for video in videos %}
        <div style="margin: 20px; padding: 20px; border: 1px solid #ccc; display:inline-block;">
            <h3>{{ video.title }}</h3>
            <video width="320" height="240" controls>
                <source src="{{ video.url }}" type="video/mp4">
                Your browser does not support the video tag.
            </video>
        </div>
    {% endfor %}
</body>
</html>
"""

@app.route('/')
def index():
    # 1. DB에서 영상 목록 조회
    videos_db = Video.query.all()
    videos_display = []
    
    # 2. 각 영상에 대해 S3 Presigned URL 생성
    for v in videos_db:
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': S3_BUCKET, 'Key': v.s3_key},
            ExpiresIn=3600 # 1시간 유효
        )
        videos_display.append({'title': v.title, 'url': url})

    return render_template_string(HTML_TEMPLATE, videos=videos_display, pod_name=os.getenv("HOSTNAME"))

# 헬스체크
@app.route('/health')
def health():
    return "OK", 200

if __name__ == '__main__':
    # 최초 실행 시 테이블 자동 생성 (데모용)
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=8080)