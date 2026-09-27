from django.urls import path, include, re_path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

from common.media import serve_media

urlpatterns = [
    # API Version 1 routes (auth + profile live in accounts)
    path('api/v1/', include('accounts.urls')),
    # Student dashboard + video upload
    path('api/v1/', include('students.urls')),
    # Coach video review
    path('api/v1/', include('coaches.urls')),

    # OpenAPI 3 Schema & Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # Uploaded media (videos, profile images) with HTTP byte-range support.
    re_path(r'^media/(?P<path>.*)$', serve_media),
]
