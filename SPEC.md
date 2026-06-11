# SPEC.md — 클래스콕 강좌 자동 등록 시스템

> 키즈와플 오감팡팡 | 전월 데이터 상속 및 클라우드 배포 기반 강좌 자동 등록 시스템  
> 최종 수정: 2026-06-11

---

## 1. Commands

### 로컬 개발

```bash
# 로컬 Streamlit 앱 구동 (개발·디버깅용)
streamlit run app.py

# Playwright headed 모드 (브라우저 화면 직접 모니터링)
python engine/bot/run_local.py --headed

# Playwright headless 모드 (CI 환경과 동일)
python engine/bot/run_local.py --headless

# 공휴일 스케줄 계산 단독 실행
python engine/scheduler/holiday_checker.py --month 2026-07

# Excel 파서 단독 실행 (파싱 결과 확인)
python engine/parser/excel_parser.py --instructor "최보라T" --month 7
```

### 배포 (GitHub Push → 자동 트리거)

```bash
# Streamlit Community Cloud 자동 재배포 트리거
git add .
git commit -m "feat: 강좌 등록 로직 업데이트"
git push origin main

# GitHub Actions 수동 트리거 (대시보드 버튼 없이 CLI에서 직접 실행)
gh workflow run classcok_register.yml \
  --field branch_id=dongtan \
  --field target_month=2026-07
```

---

## 2. Configuration Files

### 2-1. `vercel.json` (Vercel 루트 설정)

> ⚠️ **아키텍처 주의**: Vercel은 Python Streamlit 런타임을 네이티브 지원하지 않습니다.
> 아래 구성은 `/api/*` 경로만 Vercel Serverless Function으로 처리하고,
> 대시보드 UI 본체는 **Streamlit Community Cloud**에 별도 배포합니다.
> Vercel은 경량 API 게이트웨이(상태 확인, Webhook 수신) 역할만 담당합니다.

```json
{
  "version": 2,
  "builds": [
    {
      "src": "api/*.py",
      "use": "@vercel/python",
      "config": {
        "maxLambdaSize": "50mb"
      }
    }
  ],
  "routes": [
    {
      "src": "/api/status",
      "dest": "/api/status.py"
    },
    {
      "src": "/api/trigger",
      "dest": "/api/trigger.py"
    },
    {
      "src": "/api/log",
      "dest": "/api/log.py"
    }
  ],
  "env": {
    "FIREBASE_PROJECT_ID": "@firebase_project_id",
    "CLOUDINARY_CLOUD_NAME": "@cloudinary_cloud_name",
    "GITHUB_PAT": "@github_pat",
    "ANTHROPIC_API_KEY": "@anthropic_api_key"
  },
  "functions": {
    "api/*.py": {
      "maxDuration": 10
    }
  }
}
```

| 엔드포인트 | 역할 | 최대 실행시간 |
|---|---|---|
| `GET /api/status` | Firestore에서 실행 로그 조회 | 3초 |
| `POST /api/trigger` | GitHub Actions Dispatch API 호출 | 5초 |
| `GET /api/log` | 최근 등록 결과 조회 | 3초 |

### 2-2. `requirements.txt`

```txt
# ── Streamlit Dashboard ──────────────────────────────
streamlit==1.35.0
streamlit-autorefresh==1.0.1

# ── Firebase / Firestore ─────────────────────────────
firebase-admin==6.5.0
google-cloud-firestore==2.16.0

# ── Excel Parser ─────────────────────────────────────
openpyxl==3.1.2

# ── Web Automation ───────────────────────────────────
playwright==1.44.0

# ── Image Storage ────────────────────────────────────
cloudinary==1.40.0

# ── AI Self-Healing ──────────────────────────────────
anthropic==0.28.0

# ── Utilities ────────────────────────────────────────
python-dotenv==1.0.1
requests==2.32.3
cryptography==42.0.8
aiohttp==3.9.5
```

---

## 3. Data Schema (Trend Bridge)

### 3-1. Firebase Firestore 스키마

```
/branches/{branch_id}/
  ├── name: string                   # "동탄본점" | "수원점" | "운정점"
  ├── region: string                 # "경기도 화성시"
  │
  └── /instructors/{instructor_id}/
        ├── name: string             # "최보라"
        ├── day_of_week: string      # "화" | "수" | "목" | "금" | "토"
        ├── time_slot: string        # "10:30~11:20"
        ├── recommended_age: string  # "18~36개월"
        ├── capacity: number         # 8
        ├── excel_data_path: string  # "최보라T" (엑셀 시트명과 1:1 매핑)
        │
        └── /courses/{YYYYMM}/
              ├── prev_lecture_name: string    # 전월 마지막 강의명 (상속 기준)
              ├── cloudinary_thumb_url: string # 대표 썸네일 이미지 URL
              ├── holiday_week: number | null  # 공휴일 발생 주차 (null=없음)
              ├── course_type: string          # "regular" | "special_oneday"
              ├── registered_at: timestamp
              ├── status: string               # "pending"|"in_progress"|"done"|"error"
              │
              └── weeks: array
                    [
                      {
                        week: number,           # 1 | 2 | 3 | 4
                        title: string,          # 수업 주제 (C열)
                        content: string,        # 활동 내용 (D열)
                        supplies: string,       # 준비물 (E열, 촉감놀이 자동 추가)
                        sensory_play: boolean,  # 촉감놀이 여부
                        sensory_material: string | null,  # 촉감 재료명
                        status: string          # "pending"|"done"|"error"
                      }
                    ]

/sessions/
  ├── cookies_encrypted: string      # AES-256 암호화된 클래스콕 세션 쿠키
  ├── last_valid: timestamp
  └── expires_at: timestamp

/logs/{run_id}/
  ├── branch_id: string
  ├── target_month: string           # "2026-07"
  ├── triggered_by: string           # "dashboard" | "cli"
  ├── started_at: timestamp
  ├── finished_at: timestamp | null
  ├── status: string                 # "running"|"success"|"partial"|"failed"
  └── steps: array
        [{ timestamp, message, level, screenshot_url }]
```

### 3-2. 로컬 `class_config.json` 스키마

Firestore 미연결 환경(오프라인 개발·테스트)에서 동작하는 fallback 설정 파일입니다.  
**이 파일은 `.gitignore`에 반드시 포함하여 커밋하지 않습니다.**

```json
{
  "branch_id": "dongtan",
  "branch_name": "동탄본점",
  "instructors": [
    {
      "instructor_id": "choi_bora",
      "name": "최보라",
      "day_of_week": "화",
      "time_slot": "10:30~11:20",
      "recommended_age": "18~36개월",
      "capacity": 8,
      "excel_data_path": "최보라T",
      "prev_lecture_name": "버블버블 깨끗하게!",
      "cloudinary_thumb_url": "https://res.cloudinary.com/{cloud}/image/upload/v1/kidzwaffle/choi_bora_thumb.jpg"
    }
  ],
  "excel_file_path": "./data/키즈와플_강사_수업주제_최종.xlsx",
  "target_month": "2026-07",
  "holiday_api_key": ""
}
```

---

## 4. Project Structure

```
classcok-automation/
│
├── app.py                          # Streamlit 대시보드 진입점
│
├── /src                            # Streamlit 웹 프론트엔드
│   ├── pages/
│   │   ├── 01_dashboard.py         # 메인 제어 대시보드
│   │   ├── 02_preview.py           # 강좌 데이터 프리뷰 및 컨펌
│   │   ├── 03_logs.py              # 실행 로그 모니터링
│   │   └── 04_settings.py          # 강사 마스터 데이터 관리
│   ├── components/
│   │   ├── instructor_card.py      # 강사별 등록 상태 카드 컴포넌트
│   │   ├── week_table.py           # 주차별 커리큘럼 테이블
│   │   └── log_stream.py           # 실시간 로그 스트림 (Firestore 폴링)
│   └── utils/
│       ├── firebase_client.py      # Firestore 연결 및 CRUD
│       ├── github_dispatch.py      # GitHub Actions Dispatch API 호출
│       └── session_manager.py      # 쿠키 암호화/복호화
│
├── /engine                         # 자동화 핵심 엔진
│   ├── /bot                        # Playwright 자동화 봇
│   │   ├── run_local.py            # 로컬 실행 진입점 (--headed/--headless)
│   │   ├── classcok_client.py      # 클래스콕 어드민 페이지 조작 로직
│   │   ├── login_handler.py        # 로그인 + SMS 2차 인증 + 쿠키 저장
│   │   └── form_filler.py          # 강좌 등록 폼 자동 입력
│   │
│   ├── /scheduler                  # 공휴일 스케줄러
│   │   ├── holiday_checker.py      # data.go.kr 공휴일 API 대조
│   │   └── week_splitter.py        # 정규 3주 / 원데이 특강 1주 분기 로직
│   │
│   └── /parser                     # 엑셀 파서
│       ├── excel_parser.py         # 강사별 시트 파싱 + 월별 주차 추출
│       └── sensory_detector.py     # (*XXX 촉감놀이) 패턴 감지 + 재료 추출
│
├── /api                            # Vercel Serverless Functions (경량 게이트웨이)
│   ├── status.py                   # GET /api/status
│   ├── trigger.py                  # POST /api/trigger
│   └── log.py                      # GET /api/log
│
├── /tmp                            # 임시 다운로드 버퍼 (gitignore 적용)
│   └── .gitkeep                    # 폴더 구조 유지용 (내용물은 커밋 안 함)
│   # Cloudinary URL → 로컬 파일로 임시 다운로드 후 Playwright가 파일 업로드
│   # 업로드 완료 후 즉시 삭제. 민감 이미지 잔류 방지.
│
├── /data                           # 엑셀 원본 파일 저장 (gitignore 적용)
│   └── .gitkeep
│
├── /.github/workflows/
│   └── classcok_register.yml       # GitHub Actions 자동화 워크플로우
│
├── vercel.json                     # Vercel 게이트웨이 설정
├── requirements.txt                # Python 패키지 의존성
├── .env.example                    # 환경변수 템플릿 (실제 값 없음, 커밋 가능)
├── .gitignore                      # 보안 민감 파일 제외 목록
├── SPEC.md                         # 본 문서
└── README.md
```

---

## 5. Boundaries & Cloud Security Rules

### 절대 금지 사항

| 규칙 | 위반 시 결과 |
|---|---|
| 유료 API 무단 결제 | Claude API는 사용량 과금 — 월 예산 상한 설정 필수 |
| 소스코드 내 API 키 하드코딩 | GitHub 공개 레포 노출 시 즉시 계정 도용 위험 |
| `/tmp`, `/data` 폴더 커밋 | 수강생 개인정보 및 세션 쿠키 유출 위험 |
| `class_config.json` 커밋 | 지점 운영 정보 노출 |

### 환경변수 관리 원칙

**로컬 개발**: `.env` 파일 사용 (`.gitignore`에 포함)  
**Streamlit Cloud**: Secrets 대시보드 → `[secrets]` 토믈(TOML) 형식으로 등록  
**Vercel**: Dashboard → Environment Variables 등록  
**GitHub Actions**: Repository → Settings → Secrets and variables → Actions

```bash
# .env.example (커밋 가능 — 실제 값 없음)
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_PRIVATE_KEY=your-private-key
CLOUDINARY_CLOUD_NAME=your-cloud-name
CLOUDINARY_API_KEY=your-api-key
CLOUDINARY_API_SECRET=your-api-secret
ANTHROPIC_API_KEY=your-anthropic-key
GITHUB_PAT=your-github-personal-access-token
HOLIDAY_API_KEY=your-data-go-kr-key
SESSION_ENCRYPT_KEY=your-32-byte-aes-key
CLASSCOK_ID=your-classcok-id
CLASSCOK_PW=your-classcok-password
```

### `.gitignore` 핵심 항목

```gitignore
# 환경변수
.env
.env.local
.streamlit/secrets.toml

# 보안 설정
class_config.json
cookies.json
firebase-adminsdk-*.json

# 임시 파일
/tmp/*
!/tmp/.gitkeep
/data/*
!/data/.gitkeep

# Python
__pycache__/
*.pyc
.venv/

# OS
.DS_Store
```

---

## 6. Anti-Bot Strategy

### 6-1. Persistent Context (세션 재사용)

클래스콕 어드민 로그인 → SMS 2차 인증 → 세션 확립 후, Playwright의 `browser_context` 쿠키를 추출하여 **AES-256 암호화** 후 Firestore에 저장합니다. 이후 실행 시 쿠키를 복호화하여 `browser_context`에 주입함으로써 재로그인 없이 세션을 재사용합니다.

```python
# 쿠키 저장 방식 (개념)
context.storage_state(path="cookies_raw.json")   # Playwright 추출
encrypted = aes_encrypt(cookies_raw, key=SECRET)  # AES-256 암호화
firestore.collection("sessions").document("main").set({"cookies_encrypted": encrypted})

# 쿠키 복원 방식
encrypted = firestore.collection("sessions").document("main").get()
cookies_raw = aes_decrypt(encrypted, key=SECRET)  # 복호화
context = browser.new_context(storage_state=cookies_raw)  # 세션 주입
```

세션 만료 감지 시: 대시보드에 "재인증 필요" 배너 표시 → HITL 1회 SMS 입력 → 재저장.

### 6-2. 인간 모방형 무작위 딜레이

모든 클릭, 입력, 페이지 이동 사이에 무작위 딜레이를 삽입하여 봇 탐지를 회피합니다.

```python
import asyncio, random

async def human_delay(min_ms: float = 100, max_ms: float = 300):
    await asyncio.sleep(random.uniform(min_ms, max_ms) / 1000)

# 사용 예
await page.click("#submit-btn")
await human_delay(100, 300)       # 클릭 후 100~300ms 대기
await page.fill("#input-field", text)
await human_delay(150, 400)       # 타이핑 후 150~400ms 대기
```

페이지 로딩 대기는 `waitForSelector` + `networkidle` 조합으로 처리하며, 고정 `sleep`은 사용하지 않습니다.

### 6-3. XPath 중심 유연한 셀렉터 설계

클래스콕 어드민의 동적 ID 변동에 대응하기 위해 CSS ID 셀렉터 의존을 최소화하고 XPath 및 텍스트 기반 셀렉터를 우선 사용합니다.

```python
# ❌ 취약 (동적 ID 변동 시 즉시 브레이크)
await page.click("#lecture-form-submit-btn-7f3a")

# ✅ 권장 (구조·텍스트 기반, 변동에 강함)
await page.click("//button[contains(text(), '등록')]")
await page.click("//form[@class='lecture-form']//button[@type='submit']")
await page.fill("//input[preceding-sibling::label[contains(text(), '강의명')]]", title)
```

셀렉터 오류 발생 시 Claude API Self-Healing 엔진이 현재 페이지 DOM 스냅샷을 분석하여 대체 셀렉터를 자동 생성하고 1회 재시도합니다.

---

## 7. Vercel 제약 우회 전략 (예외 처리)

### 7-1. 핵심 제약 목록

| 제약 | 상세 | Vercel 무료 티어 한도 |
|---|---|---|
| 실행시간 타임아웃 | Serverless Function 최대 실행시간 | **10초** |
| 번들 크기 | 함수당 배포 패키지 최대 크기 | **50MB** |
| Playwright 브라우저 바이너리 | Chromium 바이너리 단독 크기 | **~170MB** (한도 초과) |
| Python 런타임 | Streamlit 지원 여부 | **미지원** |
| 상태 유지 | 함수 간 메모리 공유 불가 | Stateless 강제 |

### 7-2. 제약별 우회 전략

#### ① Playwright 브라우저 바이너리 (170MB > 50MB 한도)

**전략: Vercel에서 Playwright를 절대 실행하지 않는다.**

Playwright 전체를 **GitHub Actions Ubuntu Runner**에서 실행합니다. Vercel의 `/api/trigger.py`는 GitHub Dispatch API를 호출(~1초)하는 경량 프록시 역할만 수행하며, 실제 브라우저 구동은 Actions Runner 환경에서 이루어집니다.

```
[대시보드 버튼 클릭]
      ↓
[Vercel /api/trigger.py]   ← 실행시간 < 3초, 패키지 < 1MB
  POST github.com/repos/.../dispatches
      ↓
[GitHub Actions Runner]    ← Ubuntu 환경, 용량 제한 없음
  playwright install chromium
  python engine/bot/run_local.py --headless
```

#### ② Serverless Function 10초 타임아웃

**전략: 타임아웃이 발생할 수 있는 작업을 Vercel에 배치하지 않는다.**

Vercel 함수는 오직 3가지 단기 작업만 수행합니다:
- Firestore 읽기 (< 1초)
- GitHub Dispatch API 호출 (< 2초)
- 로그 조회 (< 1초)

장기 실행 작업(Playwright, Excel 파싱, Claude API 호출)은 모두 GitHub Actions에서 처리하며, 진행 상태는 Firestore를 통해 대시보드에 폴링(2초 간격)합니다.

#### ③ Streamlit — Vercel 미지원

**전략: Streamlit Community Cloud로 분리 배포.**

| 역할 | 플랫폼 | 이유 |
|---|---|---|
| 대시보드 UI (app.py) | Streamlit Community Cloud | Python 네이티브, GitHub 연동 자동 재배포, 무료 |
| 경량 API 게이트웨이 | Vercel | 빠른 응답, 전 세계 CDN |
| 자동화 Runner | GitHub Actions | 브라우저 바이너리 제한 없음, 2,000분/월 무료 |

#### ④ 상태 비저장(Stateless) 문제

**전략: Firestore를 공유 상태 저장소로 사용.**

모든 실행 상태(진행률, 로그, 쿠키)는 Vercel 함수 메모리가 아닌 Firestore에 기록합니다. 어떤 함수 인스턴스가 호출되어도 동일한 상태를 읽고 쓸 수 있습니다.

#### ⑤ 쿠키 만료 / 세션 단절 예외 처리

```
실행 시작
  └─ 쿠키 로드 → 유효성 검증 페이지 접속
       ├─ 성공: 자동화 계속 진행
       └─ 실패(만료/리디렉션):
            ├─ Firestore logs에 "SESSION_EXPIRED" 기록
            ├─ 대시보드에 "재인증 필요" 배너 표시
            └─ 자동화 중단 → 사용자 HITL 개입 요청
```

#### ⑥ Claude Self-Healing 예외 처리

```
Playwright 셀렉터 오류(TimeoutError)
  └─ DOM 스냅샷 캡처
       └─ Claude API 호출: "다음 DOM에서 '등록' 버튼의 XPath를 반환해줘"
            ├─ 성공: 새 셀렉터로 1회 재시도 → Firestore에 셀렉터 업데이트
            └─ 실패: 스크린샷 Cloudinary 업로드 → 로그에 URL 기록 → 중단
```

---

## 8. 비용 구조 요약

| 서비스 | 역할 | 무료 한도 | 유료 전환 기준 |
|---|---|---|---|
| Streamlit Community Cloud | 대시보드 UI | 앱 1개 무제한 | 커스텀 도메인 필요 시 |
| GitHub Actions | 자동화 Runner | 2,000분/월 | 초과 시 분당 $0.008 |
| Vercel | API 게이트웨이 | 100GB 대역폭/월 | 초과 시 |
| Firebase Firestore | DB | 1GiB / 50K reads/일 | 초과 시 |
| Cloudinary | 이미지 저장 | 25GB / 25K 변환/월 | 초과 시 |
| data.go.kr 공휴일 API | 공휴일 조회 | 완전 무료 | — |
| **Claude API** | Self-Healing | **없음 (종량제)** | **월 예산 상한 필수 설정** |

> **Claude API 비용 제어**: Anthropic 콘솔 → Usage Limits → Monthly budget cap 설정.  
> 예상 사용량: 월 10~20회 호출 (오류 발생 시에만 호출), 약 ₩500~₩2,000/월 예상.
