from django.urls import path

from students.views import (
    StudentDashboardView,
    StudentVideoUploadView,
    UnifiedVideoListView,
    UnifiedVideoDetailView,
)

urlpatterns = [
    path('videos/', UnifiedVideoListView.as_view(), name='video-list'),
    path('videos/<int:video_id>/', UnifiedVideoDetailView.as_view(), name='video-detail'),
    path('student/dashboard/', StudentDashboardView.as_view(), name='student-dashboard'),
    path('student/videos/', StudentVideoUploadView.as_view(), name='student-video-upload'),
]
