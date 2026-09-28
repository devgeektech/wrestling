# Wrestling Guide – Python Backend API

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![Django Version](https://img.shields.io/badge/django-4.2-green.svg)](https://www.djangoproject.com/)
[![License](https://img.shields.io/badge/license-MIT-informational.svg)](LICENSE)

Backend REST API for the **Wrestling Guide** mobile application. Built using Python, Django, Django REST Framework, SimpleJWT authentication, and OpenAPI/Swagger documentation.

---

## 🚀 Features

- **Custom Email Authentication**: Uses email as the primary login credential instead of usernames.
- **Role-Based Access Control (RBAC)**: Distinct permissions for `COACH` and `STUDENT` roles.
- **Coach Architecture**: Single active coach initialization with DB architecture ready for multi-coach scaling. No public coach registration.
- **Automatic Coach Assignment**: New students are automatically assigned to the active coach upon registration.
- **JWT Authentication**: Short-lived access tokens (30 minutes) and long-lived refresh tokens (7 days).
- **Standardized API Envelope**: All responses follow `{ "success": bool, "message": str, "data": dict/list, "errors": dict/list }`.
- **Security & Protection**: Anti-enumeration error messages, rate limiting (throttling), strong password validation, and password reuse prevention.
- **Interactive Swagger Documentation**: Built-in OpenAPI 3 schema and Swagger UI powered by `drf-spectacular`.

---

## 🛠️ Technology Stack

- **Python**: `3.8+`
- **Backend Framework**: `Django 4.2 LTS` & `Django REST Framework 3.15`
- **Authentication**: `djangorestframework-simplejwt`
- **API Documentation**: `drf-spectacular`
- **Database**: PostgreSQL 14+ (required for all environments)
- **Security**: `django-cors-headers`, `python-dotenv`, DRF Throttling

---

## 📋 Installation & Setup

### 1. Prerequisites

Ensure you have Python 3.8+ installed on your system.

### 2. Clone Repository & Setup Virtual Environment

```bash
git clone <repository_url>
cd wrestling
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Copy the template environment file:

```bash
cp .env.example .env
```

Review and adjust `.env` variables as needed:

| Variable | Description | Default |
| :--- | :--- | :--- |
| `SECRET_KEY` | Django secret key | Development default |
| `DEBUG` | Enable debug mode | `True` |
| `ALLOWED_HOSTS` | Allowed host headers | `localhost,127.0.0.1,0.0.0.0` |
| `DATABASE_NAME` | PostgreSQL database name | `wrestling_db` |
| `DATABASE_USER` | PostgreSQL username | `postgres` |
| `DATABASE_PASSWORD` | PostgreSQL password | `postgres` |
| `DATABASE_HOST` | PostgreSQL host address | `localhost` |
| `DATABASE_PORT` | PostgreSQL port | `5432` |
| `CORS_ALLOWED_ORIGINS` | Allowed CORS origins | `http://localhost:3000,http://127.0.0.1:3000` |
| `ACCESS_TOKEN_LIFETIME_MINUTES` | JWT access token TTL | `30` |
| `REFRESH_TOKEN_LIFETIME_DAYS` | JWT refresh token TTL | `7` |

---

## 🗄️ Database Setup & Migrations

### Prerequisites
Ensure PostgreSQL is running and the database is created:

```bash
# Start PostgreSQL service
sudo service postgresql start

# Create database
sudo -u postgres psql -c "CREATE DATABASE wrestling_db;"
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'postgres';"
```

### Run Migrations

```bash
python manage.py migrate
```

---

## 👤 Seed Initial Coach User

To initialize the coach account, run the seed command with required `--email` and `--password` (no defaults are shipped in the repo):

```bash
python manage.py create_initial_coach --email your-coach@example.com --password "YourSecurePassword"
```

Optional name flags:

```bash
python manage.py create_initial_coach --email your-coach@example.com --password "YourSecurePassword" --first-name John --last-name Coach
```

There is **no public coach registration** yet. Coach registration code is prepared and gated by `ALLOW_COACH_REGISTRATION=False`. Enable later when needed.

---

## 🏃 Running Development Server

Start the Django local development server:

```bash
python manage.py runserver 8000
```

The API will be accessible at `http://127.0.0.1:8000/`.

---

## Postman

Import the ready-made collection and local environment from the `postman/` folder:

1. Open Postman → **Import** → select:
   - `postman/Wrestling_Guide_API.postman_collection.json`
   - `postman/Wrestling_Guide_Local.postman_environment.json`
2. Select the **Wrestling Guide Local** environment (top-right).
3. Confirm `base_url` (default `http://127.0.0.1:8000`) and set passwords if needed.
4. Run **Auth → Login (Student)** or **Login (Coach)** — tests save `access_token` / `refresh_token`.
5. Use Student upload and Coach review requests; scripts can populate `video_id` / `frame_id`.

For Tailscale Funnel, set `base_url` to your public HTTPS URL instead of localhost.

---

## 🌐 Live via Tailscale Funnel

Expose this machine’s Django API on the public internet with a Tailscale HTTPS URL (e.g. `https://<machine>.<tailnet>.ts.net`). The PC must stay on with Tailscale connected, PostgreSQL running, and Django listening.

### Prerequisites

1. [Tailscale](https://tailscale.com/download) installed and signed in
2. Funnel enabled for your tailnet (Tailscale admin may prompt you the first time)
3. PostgreSQL running and migrations applied locally

### 1. Start the API (localhost only)

From the project root:

```powershell
.\scripts\start-tailscale-api.ps1
```

This runs `python manage.py runserver 127.0.0.1:8000` (required so Funnel can proxy to Django).

### 2. Enable Tailscale Funnel

In a **second** terminal:

```powershell
tailscale funnel --bg 8000
```

Note the printed HTTPS URL and MagicDNS hostname.

### 3. Update `.env` for the Funnel host

Replace placeholders with your real Funnel hostname:

```env
ALLOWED_HOSTS=localhost,127.0.0.1,your-machine.your-tailnet.ts.net
CSRF_TRUSTED_ORIGINS=https://your-machine.your-tailnet.ts.net
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,https://your-machine.your-tailnet.ts.net
```

Restart the API script after changing `.env`.

### 4. Verify

- Swagger: `https://<funnel-host>/api/docs/`
- Login: `POST https://<funnel-host>/api/v1/auth/login/`

### Stop Funnel

```powershell
tailscale funnel reset
```

---

## 📖 API Documentation (Swagger)

Interactive Swagger UI and OpenAPI 3 schema endpoints:

- **Swagger UI**: [`http://127.0.0.1:8000/api/docs/`](http://127.0.0.1:8000/api/docs/)
- **OpenAPI Schema**: [`http://127.0.0.1:8000/api/schema/`](http://127.0.0.1:8000/api/schema/)
- **ReDoc UI**: [`http://127.0.0.1:8000/api/redoc/`](http://127.0.0.1:8000/api/redoc/)

---

## 📡 API Endpoint Summary for Mobile Developers

Base API Path: `/api/v1/`

### 🔑 Authentication (Common)

| Method | Endpoint | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/auth/login/` | Login with email + password (coach or student). Send current `fcm_token` + optional `platform`; token is updated and returned with `user.role` | None |
| `POST` | `/api/v1/auth/register/` | Student registration. Send `fcm_token` + optional `platform`; token is saved and returned with JWT + `user`. Sends welcome email. | None |
| `POST` | `/api/v1/auth/forgot-password/` | Forgot password (email only). Works for coach and student; emails a one-time reset token (expires in 1 hour) | None |
| `POST` | `/api/v1/auth/reset-password/` | Reset password with `uid`, `token`, `new_password`. Token invalid after use | None |
| `POST` | `/api/v1/auth/token/refresh/` | Refresh JWT access token | None |

**Login note:** Mobile does **not** send `role`. Backend looks up the account and returns role in the response.

**FCM flow (no separate token API):**
1. **Register:** app gets FCM token → `POST /auth/register/` with `fcm_token` (+ `platform`) → backend saves → response includes `fcm_token` / `platform`
2. **Login:** app gets current FCM token → `POST /auth/login/` with `fcm_token` (+ `platform`) → backend upserts → response includes updated `fcm_token` / `platform`

`platform` values: `ios` / `android` / `unknown`. Omit `fcm_token` only if push is unavailable; then response `fcm_token` is `null`.

**Push notifications (FCM):** When device tokens exist, the backend sends:
- Coach: video ready for review (when AI finishes → `PENDING_REVIEW`)
- Student: analysis complete (same moment)
- Student: video approved by coach

Requires `FIREBASE_CREDENTIALS_FILE` pointing at a Firebase service account JSON. Without it, pushes are skipped (logged only).

### 👤 Profile (Common — coach & student)

| Method | Endpoint | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/auth/profile/` | View own profile (`role`, `coach_id`, `profile_image` URL) | Bearer JWT |
| `PATCH` | `/api/v1/auth/profile/` | Edit profile fields and/or upload `profile_image` (JSON or multipart) | Bearer JWT |
| `POST` | `/api/v1/auth/change-password/` | Change password | Bearer JWT |

### Videos (Common list & detail)

Shared list/detail for both roles (JWT decides the queryset):

| Method | Endpoint | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/videos/` | **STUDENT:** own videos. **COACH:** assigned videos (default pending; `?review_status=`). Optional `?q=` search (title/notes; coach also student name/email) | Bearer JWT (student or coach) |
| `GET` | `/api/v1/videos/<id>/` | **STUDENT:** own detail (analysis if APPROVED). **COACH:** assigned detail + full frames | Bearer JWT (student or coach) |

### 🏠 Student Dashboard & Videos

Requires student JWT (`role=STUDENT`).

| Method | Endpoint | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/student/dashboard/` | Home: profile summary, video counts by status, recent videos | Bearer JWT (student) |
| `POST` | `/api/v1/student/videos/` | Upload video (`multipart`: `video`, `title`, optional `notes_to_coach`) → status `UPLOADED`. No API file-size limit (formats: mp4/mov/webm/m4v). | Bearer JWT (student) |

**Video status flow (auto after upload):**  
`UPLOADED` → Gemini Flash AI → `PROCESSING` → `PENDING_REVIEW` → coach **approve** → `APPROVED` (or **reject** → `REJECTED`). If Gemini cannot produce analysis, status becomes `FAILED` with `failure_reason`.

**AI analysis (Gemini Flash):**
- Set `GEMINI_API_KEY=...`, optional `GEMINI_MODEL=gemini-3.6-flash`.
- Install **ffmpeg** / **ffprobe** on PATH (ffprobe grounds the prompt with real fps/duration; ffmpeg extracts key-moment screenshots).
- Gemini returns JSON only (`match_analysis` + `frames`); Python maps `wrestler_1/2` → API `wrestler_blue/red` and saves stills from the video file.
- Soft cap: `AI_MAX_KEY_MOMENTS` (default 40). Tests mock Gemini (`AI_ANALYSIS_SYNC=True`).

- Poll `GET /api/v1/videos/<id>/` for Processing / Pending screens.
- `analysis_ready=true` when AI finished; full `analysis` (movements/tips) is returned to the **student only when `status=APPROVED`**.
- `file_url` is an absolute `/media/...` URL for playback (same pattern as profile images). `screenshot_file` / `screenshot_url` are set when ffmpeg captures a still.

### Coach Videos (Review)

Requires coach JWT (`role=COACH`). Videos are scoped to `coach_id` = logged-in coach. List/detail: `GET /api/v1/videos/` and `GET /api/v1/videos/<id>/`.

| Method | Endpoint | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/coach/users/` | List students assigned to this coach | Bearer JWT (coach) |
| `POST` | `/api/v1/coach/videos/<id>/review/` | `{ "action": "approve"\|"reject", "comment": "optional" }`. Emails the student when review is ready. | Bearer JWT (coach) |
| `PATCH` | `/api/v1/coach/videos/<id>/frames/<frame_id>/` | Edit AI frame fields + `coaching_prescription` (only while PENDING) | Bearer JWT (coach) |
| `PATCH` | `/api/v1/coach/videos/<id>/frames/<frame_id>/comment/` | Update per-frame `coaching_prescription` only (PENDING) | Bearer JWT (coach) |
| `DELETE` | `/api/v1/coach/videos/<id>/frames/<frame_id>/comment/` | Clear per-frame `coaching_prescription` (frame stays; PENDING) | Bearer JWT (coach) |

Each analysis includes top-level `match_analysis` (`event_type`, `match_duration`, `wrestlers`, `winner`, `finish`, `summary`) plus `frames[]` items: `timestamp` (`MM:SS`), `phase`, `visual_description`, `technical_evaluation` (blue/red), `coaching_prescription`, `coach_edited_at`, `screenshot_file`, `screenshot_url`.

---

## 🧪 Automated Testing

```bash
python manage.py test accounts.tests.test_auth students.tests.test_student coaches.tests.test_coach
```
