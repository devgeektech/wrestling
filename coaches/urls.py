from django.urls import path

from coaches.views import (
    CoachUserListView,
    CoachVideoReviewView,
    CoachFrameUpdateView,
    CoachFrameCommentView,
)

urlpatterns = [
    path('coach/users/', CoachUserListView.as_view(), name='coach-user-list'),
    path('coach/videos/<int:video_id>/review/', CoachVideoReviewView.as_view(), name='coach-video-review'),
    path(
        'coach/videos/<int:video_id>/frames/<int:frame_id>/',
        CoachFrameUpdateView.as_view(),
        name='coach-frame-update',
    ),
    path(
        'coach/videos/<int:video_id>/frames/<int:frame_id>/comment/',
        CoachFrameCommentView.as_view(),
        name='coach-frame-comment',
    ),
]
