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

To initialize the coach account, run the seed command (uses default credentials automatically):

```bash
python manage.py create_initial_coach
```

**Default coach credentials:**

| Field | Value |
| :--- | :--- |
| Email | `coach@yopmail.com` |
| Password | `!@#coach!@#` |

There is **no public coach registration** yet. Coach registration code is prepared and gated by `ALLOW_COACH_REGISTRATION=False`. Enable later when needed.

To override with custom credentials:

```bash
python manage.py create_initial_coach --email custom@email.com --password "YourPassword" --first-name John --last-name Coach
```

---

## 🏃 Running Development Server

Start the Django local development server:

```bash
python manage.py runserver 8000
```

The API will be accessible at `http://127.0.0.1:8000/`.

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
| `POST` | `/api/v1/auth/login/` | Login with email + password. Backend returns `user.role` (`COACH` / `STUDENT`) for dashboard routing | None |
| `POST` | `/api/v1/auth/register/` | Student registration (always creates `STUDENT`) | None |
| `POST` | `/api/v1/auth/forgot-password/` | Forgot password (email only). Works for coach and student; emails a one-time reset token (expires in 1 hour) | None |
| `POST` | `/api/v1/auth/reset-password/` | Reset password with `uid`, `token`, `new_password`. Token invalid after use | None |
| `POST` | `/api/v1/auth/token/refresh/` | Refresh JWT access token | None |

**Login note:** Mobile does **not** send `role`. Backend looks up the account and returns role in the response.

### 👤 Profile (Common — coach & student)

| Method | Endpoint | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/auth/profile/` | View own profile (`role`, `coach_id`, `profile_image` URL) | Bearer JWT |
| `PATCH` | `/api/v1/auth/profile/` | Edit profile fields and/or upload `profile_image` (JSON or multipart) | Bearer JWT |
| `POST` | `/api/v1/auth/change-password/` | Change password | Bearer JWT |

---

## 🧪 Automated Testing

Run the automated auth/profile test suite:

```bash
python manage.py test accounts.tests.test_auth
```
