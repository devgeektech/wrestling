import os
from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load environment variables from .env file
load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-wrestling-guide-development-secret-key-change-in-prod')

DEBUG = os.getenv('DEBUG', 'True').lower() in ('true', '1', 't')

ALLOWED_HOSTS = [host.strip() for host in os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1,0.0.0.0').split(',') if host.strip()]

# Trust HTTPS / host headers from Tailscale Funnel (TLS terminates at Tailscale).
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv('CSRF_TRUSTED_ORIGINS', '').split(',')
    if origin.strip()
]

AUTH_USER_MODEL = 'accounts.User'

# Application definition
# Note: django.contrib.admin is intentionally omitted — no staff/admin users.
INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party apps
    'rest_framework',
    'rest_framework_simplejwt',
    'drf_spectacular',
    'corsheaders',
    'storages',

    # Local apps
    'common.apps.CommonConfig',
    'accounts.apps.AccountsConfig',
    'coaches.apps.CoachesConfig',
    'students.apps.StudentsConfig',
]

# Coach self-registration is prepared in code but disabled for now.
ALLOW_COACH_REGISTRATION = os.getenv('ALLOW_COACH_REGISTRATION', 'False').lower() in ('true', '1', 't')

# Dev-friendly email backend (password reset prints to console).
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'noreply@wrestlingguide.local')
# Include uid/token in forgot-password JSON for mobile clients (email is still sent when configured).
PASSWORD_RESET_RETURN_TOKEN_IN_RESPONSE = os.getenv(
    'PASSWORD_RESET_RETURN_TOKEN_IN_RESPONSE', 'True'
).lower() in ('true', '1', 't')

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# Database Configuration — PostgreSQL
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DATABASE_NAME', 'wrestling_db'),
        'USER': os.getenv('DATABASE_USER', 'postgres'),
        'PASSWORD': os.getenv('DATABASE_PASSWORD', 'postgres'),
        'HOST': os.getenv('DATABASE_HOST', 'localhost'),
        'PORT': os.getenv('DATABASE_PORT', '5432'),
        'OPTIONS': {
            'connect_timeout': 10,
        },
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 8,
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Password reset tokens expire after 1 hour (Django default_token_generator).
PASSWORD_RESET_TIMEOUT = 3600

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# S3 media storage (EC2 IAM role — do not set access keys on the instance).
# Enable with USE_S3=True and AWS_STORAGE_BUCKET_NAME. boto3 uses the instance
# profile automatically when AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY are unset.
USE_S3 = os.getenv('USE_S3', 'False').lower() in ('true', '1', 't')
AWS_STORAGE_BUCKET_NAME = os.getenv('AWS_STORAGE_BUCKET_NAME', '').strip()
AWS_S3_REGION_NAME = os.getenv('AWS_S3_REGION_NAME', 'eu-north-1').strip() or 'eu-north-1'
AWS_S3_SIGNATURE_VERSION = 's3v4'
AWS_S3_FILE_OVERWRITE = False
AWS_DEFAULT_ACL = None  # bucket-owner / IAM; avoid public-read ACL
AWS_QUERYSTRING_AUTH = os.getenv('AWS_QUERYSTRING_AUTH', 'True').lower() in ('true', '1', 't')
AWS_QUERYSTRING_EXPIRE = int(os.getenv('AWS_QUERYSTRING_EXPIRE', '21600'))
AWS_S3_OBJECT_PARAMETERS = {
    'CacheControl': 'max-age=86400',
}
AWS_S3_CUSTOM_DOMAIN = os.getenv('AWS_S3_CUSTOM_DOMAIN', '').strip() or None

if USE_S3 and AWS_STORAGE_BUCKET_NAME:
    STORAGES = {
        'default': {
            'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage',
            'OPTIONS': {
                'bucket_name': AWS_STORAGE_BUCKET_NAME,
                'region_name': AWS_S3_REGION_NAME,
                'default_acl': AWS_DEFAULT_ACL,
                'querystring_auth': AWS_QUERYSTRING_AUTH,
                'querystring_expire': AWS_QUERYSTRING_EXPIRE,
                'file_overwrite': AWS_S3_FILE_OVERWRITE,
                'object_parameters': AWS_S3_OBJECT_PARAMETERS,
                'signature_version': AWS_S3_SIGNATURE_VERSION,
                **(
                    {'custom_domain': AWS_S3_CUSTOM_DOMAIN}
                    if AWS_S3_CUSTOM_DOMAIN
                    else {}
                ),
            },
        },
        'staticfiles': {
            'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
        },
    }
    if AWS_S3_CUSTOM_DOMAIN:
        MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/'
    else:
        MEDIA_URL = f'https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/'
else:
    STORAGES = {
        'default': {
            'BACKEND': 'django.core.files.storage.FileSystemStorage',
        },
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    }

# Student video uploads (multipart). 0 = no API size limit.
MAX_VIDEO_UPLOAD_MB = int(os.getenv('MAX_VIDEO_UPLOAD_MB', '0'))
# Spill large multipart bodies/files to temp disk instead of RAM (not a reject limit).
_UPLOAD_MEMORY_SPILL_BYTES = 10 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = _UPLOAD_MEMORY_SPILL_BYTES
FILE_UPLOAD_MAX_MEMORY_SIZE = _UPLOAD_MEMORY_SPILL_BYTES

# AI pipeline — Gemini Flash only. Sync=true runs analysis in-process (tests).
AI_ANALYSIS_SYNC = os.getenv('AI_ANALYSIS_SYNC', 'False').lower() in ('true', '1', 't')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '').strip()
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-3.6-flash').strip() or 'gemini-3.6-flash'
AI_MAX_KEY_MOMENTS = int(os.getenv('AI_MAX_KEY_MOMENTS', '40'))

# Firebase Cloud Messaging (optional). Leave empty to skip real FCM sends.
_firebase_cred = os.getenv('FIREBASE_CREDENTIALS_FILE', '').strip()
FIREBASE_CREDENTIALS_FILE = (
    str(BASE_DIR / _firebase_cred)
    if _firebase_cred and not Path(_firebase_cred).is_absolute()
    else _firebase_cred
)

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework Configuration
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_RENDERER_CLASSES': (
        'common.renderers.StandardJSONRenderer',
    ),
    'EXCEPTION_HANDLER': 'common.exceptions.custom_exception_handler',
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_THROTTLE_CLASSES': [
        'accounts.throttles.AuthAnonRateThrottle',
        'accounts.throttles.AuthUserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '30/minute',
        'user': '100/minute',
        'auth': '10/minute',
    }
}

# Simple JWT Configuration
access_lifetime = int(os.getenv('ACCESS_TOKEN_LIFETIME_MINUTES', 30))
refresh_lifetime = int(os.getenv('REFRESH_TOKEN_LIFETIME_DAYS', 7))

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=access_lifetime),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=refresh_lifetime),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': False,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}

# OpenAPI Swagger Configuration
SPECTACULAR_SETTINGS = {
    'TITLE': 'Wrestling Guide Backend API',
    'DESCRIPTION': 'REST API documentation for the Wrestling Guide mobile application.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'SCHEMA_PATH_PREFIX': r'/api/v1/',
    'TAGS': [
        {'name': 'Authentication - Common'},
        {'name': 'Profile'},
        {'name': 'Videos - Common'},
        {'name': "Student API's"},
        {'name': "Coach API's"},
    ],
}

# CORS Configuration
CORS_ALLOWED_ORIGINS = [
    origin.strip() for origin in os.getenv(
        'CORS_ALLOWED_ORIGINS',
        'http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000'
    ).split(',') if origin.strip()
]
