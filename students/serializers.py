from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

from accounts.serializers import UserSummarySerializer
from common.media_urls import absolute_media_url
from students.models import AnalysisMovement, VideoAnalysis, WrestlingVideo

ALLOWED_VIDEO_EXTENSIONS = {'.mp4', '.mov', '.webm', '.m4v'}
ALLOWED_VIDEO_CONTENT_TYPES = {
    'video/mp4',
    'video/quicktime',
    'video/webm',
    'video/x-m4v',
    'application/octet-stream',
}


def format_timestamp(seconds):
    """Format seconds as MM:SS."""
    total = int(round(float(seconds or 0)))
    minutes, secs = divmod(max(total, 0), 60)
    return f"{minutes:02d}:{secs:02d}"


class AnalysisFrameSerializer(serializers.ModelSerializer):
    """Rich per-frame AI payload (API name: frames)."""

    timestamp = serializers.SerializerMethodField()
    screenshot_url = serializers.SerializerMethodField()
    screenshot_file = serializers.SerializerMethodField()
    coaching_prescription = serializers.CharField(source='ai_suggestion', read_only=True)

    class Meta:
        model = AnalysisMovement
        fields = (
            'id',
            'timestamp',
            'timestamp_seconds',
            'screenshot_file',
            'screenshot_url',
            'phase',
            'visual_description',
            'technical_evaluation',
            'coaching_prescription',
            'ai_score',
            'coach_edited_at',
            'sort_order',
        )
        read_only_fields = fields

    def get_timestamp(self, obj):
        return format_timestamp(obj.timestamp_seconds)

    def get_screenshot_file(self, obj):
        if not obj.frame_image:
            return None
        return obj.frame_image.name.rsplit('/', 1)[-1]

    def get_screenshot_url(self, obj):
        if not obj.frame_image:
            return None
        return absolute_media_url(obj.frame_image, self.context.get('request'))


class VideoAnalysisSerializer(serializers.ModelSerializer):
    frames = AnalysisFrameSerializer(source='movements', many=True, read_only=True)

    class Meta:
        model = VideoAnalysis
        fields = (
            'id',
            'match_analysis',
            'summary',
            'overall_score',
            'processed_at',
            'frames',
        )
        read_only_fields = fields


class CoachFrameUpdateSerializer(serializers.Serializer):
    """Partial update of AI frame fields + coaching_prescription."""

    phase = serializers.CharField(required=False, allow_blank=True, max_length=255)
    visual_description = serializers.CharField(required=False, allow_blank=True)
    technical_evaluation = serializers.JSONField(required=False)
    coaching_prescription = serializers.CharField(required=False, allow_blank=True)
    timestamp_seconds = serializers.FloatField(required=False, min_value=0)

    def validate_technical_evaluation(self, value):
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("Must be an object.")
        return value

    def update(self, instance, validated_data):
        ai_fields = ('phase', 'visual_description', 'technical_evaluation', 'timestamp_seconds')
        touched = False
        for field in ai_fields:
            if field in validated_data:
                setattr(instance, field, validated_data[field])
                touched = True
                if field == 'phase':
                    instance.movement_name = validated_data[field]
        if 'coaching_prescription' in validated_data:
            instance.ai_suggestion = validated_data['coaching_prescription']
            touched = True
        if touched:
            instance.coach_edited_at = timezone.now()
        instance.save()
        return instance


class CoachFrameCommentSerializer(serializers.Serializer):
    """Create/update per-frame coaching_prescription only."""

    coaching_prescription = serializers.CharField(required=True, allow_blank=True)


class WrestlingVideoSerializer(serializers.ModelSerializer):
    """Student-facing video payload; analysis only when APPROVED."""

    file_url = serializers.SerializerMethodField()
    analysis = serializers.SerializerMethodField()
    analysis_ready = serializers.SerializerMethodField()

    class Meta:
        model = WrestlingVideo
        fields = (
            'id',
            'title',
            'notes_to_coach',
            'status',
            'coach_review_status',
            'coach_review_comment',
            'original_filename',
            'file_size',
            'content_type',
            'file_url',
            'failure_reason',
            'analysis_ready',
            'analysis',
            'created_at',
            'updated_at',
        )
        read_only_fields = fields

    def get_file_url(self, obj):
        if not obj.video_file:
            return None
        return absolute_media_url(obj.video_file, self.context.get('request'))

    def get_analysis_ready(self, obj):
        try:
            return obj.analysis is not None
        except VideoAnalysis.DoesNotExist:
            return False

    def get_analysis(self, obj):
        if obj.status != WrestlingVideo.Status.APPROVED:
            return None
        try:
            analysis = obj.analysis
        except VideoAnalysis.DoesNotExist:
            return None
        return VideoAnalysisSerializer(analysis, context=self.context).data


class WrestlingVideoUploadSerializer(serializers.Serializer):
    """Multipart upload from Preparing → Uploading screens."""

    video = serializers.FileField(required=True)
    title = serializers.CharField(required=True, max_length=200)
    notes_to_coach = serializers.CharField(required=False, allow_blank=True, default='')

    def validate_video(self, value):
        name = getattr(value, 'name', '') or ''
        ext = ''
        if '.' in name:
            ext = '.' + name.rsplit('.', 1)[-1].lower()

        content_type = (getattr(value, 'content_type', None) or '').lower()

        if ext and ext not in ALLOWED_VIDEO_EXTENSIONS:
            raise serializers.ValidationError(
                "Unsupported video format. Allowed: mp4, mov, webm, m4v."
            )

        if content_type and content_type not in ALLOWED_VIDEO_CONTENT_TYPES:
            if not ext or ext not in ALLOWED_VIDEO_EXTENSIONS:
                raise serializers.ValidationError("Unsupported video content type.")

        if not ext and content_type not in (ALLOWED_VIDEO_CONTENT_TYPES - {'application/octet-stream'}):
            raise serializers.ValidationError("Could not determine video format.")

        return value

    def create(self, validated_data):
        request = self.context['request']
        student = request.user
        video_file = validated_data['video']
        title = validated_data['title'].strip()
        notes = (validated_data.get('notes_to_coach') or '').strip()

        return WrestlingVideo.objects.create(
            student=student,
            coach=student.coach_assigned,
            title=title,
            notes_to_coach=notes,
            video_file=video_file,
            original_filename=getattr(video_file, 'name', '') or '',
            file_size=getattr(video_file, 'size', 0) or 0,
            content_type=getattr(video_file, 'content_type', '') or '',
            status=WrestlingVideo.Status.UPLOADED,
            coach_review_status=WrestlingVideo.CoachReviewStatus.NOT_REQUIRED,
        )


class CoachWrestlingVideoSerializer(serializers.ModelSerializer):
    """Coach-facing video; always includes analysis when present."""

    file_url = serializers.SerializerMethodField()
    student = UserSummarySerializer(read_only=True)
    analysis = serializers.SerializerMethodField()
    analysis_ready = serializers.SerializerMethodField()

    class Meta:
        model = WrestlingVideo
        fields = (
            'id',
            'title',
            'notes_to_coach',
            'status',
            'coach_review_status',
            'coach_review_comment',
            'coach_reviewed_at',
            'original_filename',
            'file_size',
            'content_type',
            'file_url',
            'failure_reason',
            'student',
            'analysis_ready',
            'analysis',
            'created_at',
            'updated_at',
        )
        read_only_fields = fields

    def get_file_url(self, obj):
        if not obj.video_file:
            return None
        return absolute_media_url(obj.video_file, self.context.get('request'))

    def get_analysis_ready(self, obj):
        try:
            return obj.analysis is not None
        except VideoAnalysis.DoesNotExist:
            return False

    def get_analysis(self, obj):
        try:
            analysis = obj.analysis
        except VideoAnalysis.DoesNotExist:
            return None
        return VideoAnalysisSerializer(analysis, context=self.context).data


class CoachVideoReviewSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['approve', 'reject'])
    comment = serializers.CharField(required=False, allow_blank=True, default='')
