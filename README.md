# 키즈와플 오감팡팡 — 클래스콕 강좌 자동 등록 시스템

매달 반복되는 클래스콕 강좌 등록 작업을 자동화하는 시스템입니다.  
전월 Firebase 마스터 데이터를 상속하고, 엑셀 커리큘럼을 자동 파싱하여 등록합니다.

## 기술 스택

| 역할 | 기술 |
|---|---|
| 대시보드 UI | Streamlit Community Cloud |
| 자동화 Runner | GitHub Actions (Playwright headless) |
| API 게이트웨이 | Vercel Serverless Functions |
| 데이터베이스 | Firebase Firestore |
| 이미지 저장 | Cloudinary |
| AI Self-Healing | Anthropic Claude API |

## 로컬 실행

```bash
# 1. 가상환경 생성
python -m venv .venv && source .venv/bin/activate

# 2. 패키지 설치
pip install -r requirements.txt
playwright install chromium

# 3. 환경변수 설정
cp .env.example .env
# .env 파일에 실제 값 입력 (절대 커밋 금지)

# 4. 대시보드 실행
streamlit run app.py

# 5. 자동화 봇 로컬 실행 (headed 모드 — 브라우저 직접 확인)
python engine/bot/run_local.py --headed --branch dongtan --month 2026-07
```

## 환경변수

`.env.example` 파일을 참고하여 `.env` 파일을 생성하세요.  
클라우드 배포 시에는 각 플랫폼의 Secrets/Environment Variables에 등록합니다.

## 태스크 진행 현황

- [x] T1. 프로젝트 레포 뼈대 초기화
- [ ] T2. Excel 파서 모듈
- [ ] T3. Firebase CRUD 모듈
- [ ] T4. 공휴일 분기 엔진
- [ ] T5. Streamlit 대시보드 UI
- [ ] T6. Playwright 자동화 봇
- [ ] T7. GitHub Actions 워크플로우
- [ ] T8. 클라우드 배포 + E2E 테스트
