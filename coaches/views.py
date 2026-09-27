from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework.views import APIView

from accounts.models import User
from common.email import send_video_review_ready_email
from common.notifications import notify_video_approved
from common.permissions import IsCoach
from common.responses import success_response, error_response
from coaches.serializers import CoachStudentListSerializer
from students.models import AnalysisMovement, WrestlingVideo
from students.serializers import (
    AnalysisFrameSerializer,
    CoachFrameCommentSerializer,
    CoachFrameUpdateSerializer,
    CoachWrestlingVideoSerializer,
    CoachVideoReviewSerializer,
)


class CoachUserListView(APIView):
    permission_classes = [IsCoach]

    @extend_schema(
        summary="List assigned students",
        description=(
            "Returns students assigned to the logged-in coach "
            "(`coach_assigned` = current user)."
        ),
        responses={200: OpenApiResponse(description="Student list")},
        tags=["Coach API's"],
    )
    def get(self, request, *args, **kwargs):
        students = User.objects.filter(
            role=User.Roles.STUDENT,
            coach_assigned=request.user,
            is_active=True,
        ).order_by('first_name', 'last_name')
        serializer = CoachStudentListSerializer(
            students, many=True, context={'request': request}
        )
        return success_response("Users loaded", serializer.data)


class CoachVideoReviewView(APIView):
    permission_classes = [IsCoach]

    @extend_schema(
        summary="Approve or reject video",
        description=(
            "Body: `{ \"action\": \"approve\"|\"reject\", \"comment\": \"optional\" }`. "
            "Only when coach_review_status=PENDING."
        ),
        request=CoachVideoReviewSerializer,
        responses={
            200: OpenApiResponse(description="Review saved"),
            400: OpenApiResponse(description="Invalid state or payload"),
            404: OpenApiResponse(description="Not found"),
        },
        tags=["Coach API's"],
    )
    def post(self, request, video_id, *args, **kwargs):
        video = get_object_or_404(
            WrestlingVideo.objects.select_related('student', 'analysis').prefetch_related(
                'analysis__movements'
            ),
            id=video_id,
            coach=request.user,
        )
        if video.coach_review_status != WrestlingVideo.CoachReviewStatus.PENDING:
            return error_response(
                "Video is not pending coach review.",
                {"coach_review_status": video.coach_review_status},
            )

        serializer = CoachVideoReviewSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response("Validation failed", serializer.errors)

        action = serializer.validated_data['action']
        comment = (serializer.validated_data.get('comment') or '').strip()
        now = timezone.now()

        if action == 'approve':
            video.status = WrestlingVideo.Status.APPROVED
            video.coach_review_status = WrestlingVideo.CoachReviewStatus.APPROVED
        else:
            video.status = WrestlingVideo.Status.REJECTED
            video.coach_review_status = WrestlingVideo.CoachReviewStatus.REJECTED

        video.coach_review_comment = comment
        video.coach_reviewed_at = now
        video.save(
            update_fields=[
                'status',
                'coach_review_status',
                'coach_review_comment',
                'coach_reviewed_at',
                'updated_at',
            ]
        )
        send_video_review_ready_email(video)
        if action == 'approve':
            notify_video_approved(video)

        message = "Video approved" if action == 'approve' else "Video rejected"
        return success_response(
            message,
            CoachWrestlingVideoSerializer(video, context={'request': request}).data,
        )


class CoachFrameUpdateView(APIView):
    permission_classes = [IsCoach]

    def get_frame(self, request, video_id, frame_id):
        video = get_object_or_404(WrestlingVideo, id=video_id, coach=request.user)
        return get_object_or_404(
            AnalysisMovement.objects.select_related('analysis', 'analysis__video'),
            id=frame_id,
            analysis__video=video,
        )

    @extend_schema(
        summary="Edit AI frame + coaching_prescription",
        description=(
            "Partial update while video is PENDING review. "
            "Editable: phase, visual_description, technical_evaluation, "
            "coaching_prescription, timestamp_seconds."
        ),
        request=CoachFrameUpdateSerializer,
        responses={
            200: OpenApiResponse(description="Frame updated"),
            400: OpenApiResponse(description="Validation or locked"),
            404: OpenApiResponse(description="Not found"),
        },
        tags=["Coach API's"],
    )
    def patch(self, request, video_id, frame_id, *args, **kwargs):
        frame = self.get_frame(request, video_id, frame_id)
        video = frame.analysis.video
        if video.coach_review_status != WrestlingVideo.CoachReviewStatus.PENDING:
            return error_response(
                "Frames can only be edited while the video is pending coach review.",
                {"coach_review_status": video.coach_review_status},
            )

        serializer = CoachFrameUpdateSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response("Validation failed", serializer.errors)

        frame = serializer.update(frame, serializer.validated_data)
        return success_response(
            "Frame updated",
            AnalysisFrameSerializer(frame, context={'request': request}).data,
        )


class CoachFrameCommentView(APIView):
    """Edit or clear per-frame coaching_prescription (does not delete the frame)."""

    permission_classes = [IsCoach]

    def get_frame(self, request, video_id, frame_id):
        video = get_object_or_404(WrestlingVideo, id=video_id, coach=request.user)
        return get_object_or_404(
            AnalysisMovement.objects.select_related('analysis', 'analysis__video'),
            id=frame_id,
            analysis__video=video,
        )

    def _ensure_pending(self, video):
        if video.coach_review_status != WrestlingVideo.CoachReviewStatus.PENDING:
            return error_response(
                "Coaching prescription can only be edited while the video is pending coach review.",
                {"coach_review_status": video.coach_review_status},
            )
        return None

    @extend_schema(
        summary="Edit frame coaching_prescription",
        description=(
            "Body: `{ \"coaching_prescription\": \"...\" }`. "
            "Only while coach_review_status=PENDING."
        ),
        request=CoachFrameCommentSerializer,
        responses={
            200: OpenApiResponse(description="Coaching prescription updated"),
            400: OpenApiResponse(description="Validation or locked"),
            404: OpenApiResponse(description="Not found"),
        },
        tags=["Coach API's"],
    )
    def patch(self, request, video_id, frame_id, *args, **kwargs):
        frame = self.get_frame(request, video_id, frame_id)
        locked = self._ensure_pending(frame.analysis.video)
        if locked:
            return locked

        serializer = CoachFrameCommentSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response("Validation failed", serializer.errors)

        frame.ai_suggestion = serializer.validated_data['coaching_prescription']
        frame.coach_edited_at = timezone.now()
        frame.save(update_fields=['ai_suggestion', 'coach_edited_at'])
        return success_response(
            "Coaching prescription updated",
            AnalysisFrameSerializer(frame, context={'request': request}).data,
        )

    @extend_schema(
        summary="Clear frame coaching_prescription",
        description=(
            "Clears coaching_prescription on the frame (other AI fields remain). "
            "Only while coach_review_status=PENDING."
        ),
        responses={
            200: OpenApiResponse(description="Coaching prescription cleared"),
            400: OpenApiResponse(description="Locked"),
            404: OpenApiResponse(description="Not found"),
        },
        tags=["Coach API's"],
    )
    def delete(self, request, video_id, frame_id, *args, **kwargs):
        frame = self.get_frame(request, video_id, frame_id)
        locked = self._ensure_pending(frame.analysis.video)
        if locked:
            return locked

        frame.ai_suggestion = ''
        frame.coach_edited_at = timezone.now()
        frame.save(update_fields=['ai_suggestion', 'coach_edited_at'])
        return success_response(
            "Coaching prescription cleared",
            AnalysisFrameSerializer(frame, context={'request': request}).data,
        )
