from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse
from rest_framework import status, parsers
from rest_framework.views import APIView

from accounts.serializers import UserProfileSerializer
from common.permissions import IsStudent, IsCoachOrStudent
from common.responses import success_response, error_response
from students.models import WrestlingVideo
from students.serializers import (
    WrestlingVideoSerializer,
    WrestlingVideoUploadSerializer,
    CoachWrestlingVideoSerializer,
)
from students.services.ai_pipeline import enqueue_analysis


def build_video_list_response(request):
    """
    Shared list logic for student and coach.
    STUDENT: own videos (analysis gated by serializer until APPROVED).
    COACH: assigned videos; default review_status=PENDING; ?review_status= supported.
    Optional ?q= text search (title/notes; coach also student name/email).
    """
    user = request.user
    q = (request.query_params.get('q') or '').strip()

    if user.role == user.Roles.STUDENT:
        qs = WrestlingVideo.objects.filter(student=user)
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(notes_to_coach__icontains=q))
        data = WrestlingVideoSerializer(qs, many=True, context={'request': request}).data
        return success_response("Videos retrieved", data)

    if user.role == user.Roles.COACH:
        qs = WrestlingVideo.objects.filter(coach=user).select_related(
            'student', 'analysis'
        ).prefetch_related('analysis__movements')
        review_status = (request.query_params.get('review_status') or 'PENDING').upper()
        if review_status != 'ALL':
            qs = qs.filter(coach_review_status=review_status)
        if q:
            qs = qs.filter(
                Q(title__icontains=q)
                | Q(notes_to_coach__icontains=q)
                | Q(student__first_name__icontains=q)
                | Q(student__last_name__icontains=q)
                | Q(student__email__icontains=q)
            )
        data = CoachWrestlingVideoSerializer(qs, many=True, context={'request': request}).data
        return success_response("Videos retrieved", data)

    return error_response("Forbidden", status_code=status.HTTP_403_FORBIDDEN)


class UnifiedVideoListView(APIView):
    """Preferred shared list: GET /api/v1/videos/"""

    permission_classes = [IsCoachOrStudent]

    @extend_schema(
        summary="List videos (student or coach)",
        description=(
            "Role-based video list. "
            "STUDENT: own submissions. "
            "COACH: assigned videos (default coach_review_status=PENDING; "
            "use ?review_status=PENDING|APPROVED|REJECTED|NOT_REQUIRED|ALL). "
            "Optional ?q= searches title/notes; coach also matches student name/email."
        ),
        parameters=[
            OpenApiParameter(
                name='q',
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    'Search text. Student: title, notes_to_coach. '
                    'Coach: title, notes_to_coach, student first/last name, email.'
                ),
            ),
            OpenApiParameter(
                name='review_status',
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description='Coach only: PENDING|APPROVED|REJECTED|NOT_REQUIRED|ALL (default PENDING)',
            ),
        ],
        responses={200: OpenApiResponse(description="Video list")},
        tags=["Videos - Common"],
    )
    def get(self, request, *args, **kwargs):
        return build_video_list_response(request)


def build_video_detail_response(request, video_id):
    """
    Shared detail logic for student and coach.
    STUDENT: own video; analysis gated until APPROVED.
    COACH: assigned video; full frames + student summary.
    """
    user = request.user
    if user.role == user.Roles.STUDENT:
        video = get_object_or_404(
            WrestlingVideo.objects.select_related('analysis').prefetch_related(
                'analysis__movements'
            ),
            id=video_id,
            student=user,
        )
        data = WrestlingVideoSerializer(video, context={'request': request}).data
        return success_response("Video retrieved", data)

    if user.role == user.Roles.COACH:
        video = get_object_or_404(
            WrestlingVideo.objects.select_related('student', 'analysis').prefetch_related(
                'analysis__movements'
            ),
            id=video_id,
            coach=user,
        )
        data = CoachWrestlingVideoSerializer(video, context={'request': request}).data
        return success_response("Video retrieved", data)

    return error_response("Forbidden", status_code=status.HTTP_403_FORBIDDEN)


class UnifiedVideoDetailView(APIView):
    """Preferred shared detail: GET /api/v1/videos/<id>/"""

    permission_classes = [IsCoachOrStudent]

    @extend_schema(
        summary="Video detail (student or coach)",
        description=(
            "Role-based video detail. "
            "STUDENT: own video; full analysis only when APPROVED. "
            "COACH: assigned video with full AI frames."
        ),
        responses={
            200: OpenApiResponse(description="Video detail"),
            404: OpenApiResponse(description="Not found"),
        },
        tags=["Videos - Common"],
    )
    def get(self, request, video_id, *args, **kwargs):
        return build_video_detail_response(request, video_id)


class StudentDashboardView(APIView):
    permission_classes = [IsStudent]

    @extend_schema(
        summary="Student dashboard",
        description=(
            "Home data for the student app: basic profile, video counts by status, "
            "and the 5 most recent submissions."
        ),
        responses={200: OpenApiResponse(description="Dashboard payload")},
        tags=["Student API's"],
    )
    def get(self, request, *args, **kwargs):
        student = request.user
        videos = WrestlingVideo.objects.filter(student=student)
        status_counts = {choice.value: 0 for choice in WrestlingVideo.Status}
        for row in videos.values_list('status', flat=True):
            if row in status_counts:
                status_counts[row] += 1

        recent = videos.order_by('-created_at')[:5]
        profile = UserProfileSerializer(student, context={'request': request}).data

        return success_response(
            "Dashboard loaded",
            {
                "profile": profile,
                "stats": {
                    "total_videos": videos.count(),
                    "by_status": status_counts,
                },
                "recent_videos": WrestlingVideoSerializer(
                    recent, many=True, context={'request': request}
                ).data,
            },
        )


class StudentVideoUploadView(APIView):
    """POST-only student video upload. List/detail use GET /api/v1/videos/."""

    permission_classes = [IsStudent]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]

    @extend_schema(
        summary="Upload wrestling video",
        description=(
            "Upload a video from the Preparing screen. Send multipart fields: "
            "`video` (file), `title`, optional `notes_to_coach`. "
            "Creates a record with status=UPLOADED, then Gemini analysis moves it to "
            "PROCESSING → PENDING_REVIEW (or FAILED if analysis cannot be produced). "
            "List/detail: GET /api/v1/videos/ and GET /api/v1/videos/<id>/."
        ),
        request=WrestlingVideoUploadSerializer,
        responses={
            201: OpenApiResponse(description="Video uploaded"),
            400: OpenApiResponse(description="Validation error"),
        },
        tags=["Student API's"],
    )
    def post(self, request, *args, **kwargs):
        serializer = WrestlingVideoUploadSerializer(
            data=request.data, context={'request': request}
        )
        if serializer.is_valid():
            video = serializer.save()
            video_id = video.id
            # Sync mode runs immediately (tests). Async uses on_commit + background thread.
            if getattr(settings, 'AI_ANALYSIS_SYNC', False):
                enqueue_analysis(video_id)
                video.refresh_from_db()
            else:
                transaction.on_commit(lambda: enqueue_analysis(video_id))
            return success_response(
                "Video uploaded successfully",
                WrestlingVideoSerializer(video, context={'request': request}).data,
                status_code=status.HTTP_201_CREATED,
            )
        return error_response("Validation failed", serializer.errors)
