"""
배포에 필요한 보안 키를 로컬에서 생성한다.
출력된 값을 각 플랫폼 Secrets에 등록하세요.
생성된 키는 화면에만 표시되며 파일에 저장되지 않습니다.
"""
import secrets

key = secrets.token_hex(32)
print("\n=== SESSION_ENCRYPT_KEY (AES-256, 64자 hex) ===")
print(key)
print("\n이 값을 아래 위치에 등록하세요:")
print("  • .env 파일 → SESSION_ENCRYPT_KEY=<위 값>")
print("  • Streamlit Cloud → Secrets → SESSION_ENCRYPT_KEY = \"<위 값>\"")
print("  • GitHub → Settings → Secrets → SESSION_ENCRYPT_KEY")
print("  • Vercel → Environment Variables → SESSION_ENCRYPT_KEY\n")
