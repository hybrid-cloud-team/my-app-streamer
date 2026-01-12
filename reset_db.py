import psycopg2

# RDS 접속 정보 (본인 환경에 맞게 확인 필수)
host = "hybrid-demo-db.c4dqgm4aut3y.us-east-1.rds.amazonaws.com"
dbname = "videodb"
user = "postgres"
password = "12345678"

try:
    print("🔌 RDS 접속 시도 중...")
    conn = psycopg2.connect(host=host, database=dbname, user=user, password=password)
    cur = conn.cursor()
    
    # 기존 테이블 강제 삭제 (CASCADE 옵션으로 연관된 것까지 싹 지움)
    print("🗑️ 기존 테이블(video, user) 삭제 중...")
    cur.execute("DROP TABLE IF EXISTS video CASCADE;")
    cur.execute('DROP TABLE IF EXISTS "user" CASCADE;') 
    
    conn.commit()
    print("✅ 삭제 완료! 이제 앱(Pod)을 재시작하면 새 테이블이 자동으로 생성됩니다.")
    
    cur.close()
    conn.close()

except Exception as e:
    print(f"❌ 에러 발생: {e}")