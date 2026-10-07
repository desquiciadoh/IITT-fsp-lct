import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / 'apps'))

SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-default-key-for-dev')
ITEM_SEED_SECRET = os.environ.get('ITEM_SEED_SECRET', 'item-seed-secret-dev')
DEBUG = os.environ.get('DEBUG', 'True').lower() in ('true', '1')
DEMO_MODE = os.environ.get('DEMO_MODE', 'True').lower() in ('true', '1')

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '*').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party
    'rest_framework',
    'django_filters',
    'drf_spectacular',
    # Project apps
    'core.apps.CoreConfig',
    'identity.apps.IdentityConfig',
    'profiles.apps.ProfilesConfig',
    'assessment.apps.AssessmentConfig',
    'matching.apps.MatchingConfig',
    'outreach.apps.OutreachConfig',
    'fsp_sync.apps.FspSyncConfig',
]

MIDDLEWARE = [
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
        'DIRS': [BASE_DIR / 'templates'],
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

# --- Database ---
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB', 'fsp_draft'),
        'USER': os.environ.get('POSTGRES_USER', 'postgres'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD', 'postgres'),
        'HOST': os.environ.get('POSTGRES_HOST', 'localhost'),
        'PORT': os.environ.get('POSTGRES_PORT', '5432'),
    }
}

# --- Auth ---
AUTH_USER_MODEL = 'identity.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
]

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
]

# --- Sessions ---
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_NAME = 'sid'

# --- i18n & time ---
LANGUAGE_CODE = 'ru'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- DRF ---
REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'core.pagination.FSPPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.MultiPartParser',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
    ],
    'EXCEPTION_HANDLER': 'core.errors.fsp_exception_handler',
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'FSP Draft API',
    'DESCRIPTION': 'Reverse IT recruitment platform with verified achievement profiles (FSP)',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SCHEMA_PATH_PREFIX': '/api/',
}

# --- Celery ---
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'

# --- FSP / OIDC ---
OIDC_ISSUER = os.environ.get('OIDC_ISSUER', 'http://localhost:8090/realms/fsp')
OIDC_CLIENT_ID = os.environ.get('OIDC_CLIENT_ID', 'fsp-draft')
OIDC_CLIENT_SECRET = os.environ.get('OIDC_CLIENT_SECRET', 'dev-secret')
FSP_REGISTRY_URL = os.environ.get('FSP_REGISTRY_URL', 'http://localhost:8090/registry/v1')

# --- LLM ---
LLM_PROVIDER = os.environ.get('LLM_PROVIDER', 'fake')

# --- Public URL ---
PUBLIC_BASE_URL = os.environ.get('PUBLIC_BASE_URL', 'http://localhost:8000')

# --- Email ---
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.environ.get('SMTP_HOST', 'localhost')
EMAIL_PORT = int(os.environ.get('SMTP_PORT', '1025'))
EMAIL_USE_TLS = False
DEFAULT_FROM_EMAIL = os.environ.get('MAIL_FROM', 'noreply@fsp-draft.local')

# --- Cooldowns (days) ---
GRADE_RETRY_COOLDOWN_DAYS = 30
GRADE_PROMOTION_COOLDOWN_DAYS = 90
