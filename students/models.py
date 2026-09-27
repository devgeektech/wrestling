import os
import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


def student_video_upload_to(instance, filename):
    """Store under student_videos/<student_id>/<uuid>_<safe_name>."""
    ext = os.path.splitext(filename)[1].lower()
    safe_name = f"{uuid.uuid4().hex}{ext}"
    return f"student_videos/{instance.student_id}/{safe_name}"


def analysis_frame_upload_to(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    safe_name = f"{uuid.uuid4().hex}{ext}"
    video_id = instance.analysis.video_id
    return f"analysis_frames/{video_id}/{safe_name}"


class WrestlingVideo(models.Model):
    """
    Student wrestling video submission.

    Mobile pipeline status drives UI screens; coach_review_status is for coach queues.
    Student sees full AI results only when status=APPROVED.
    """

    class Status(models.TextChoices):
        UPLOADED = 'UPLOADED', _('Uploaded')
        PROCESSING = 'PROCESSING', _('Processing')
        PENDING_REVIEW = 'PENDING_REVIEW', _('Pending coach review')
        APPROVED = 'APPROVED', _('Approved')
        REJECTED = 'REJECTED', _('Rejected')
        FAILED = 'FAILED', _('Failed')

    class CoachReviewStatus(models.TextChoices):
        NOT_REQUIRED = 'NOT_REQUIRED', _('Not required')
        PENDING = 'PENDING', _('Pending')
        APPROVED = 'APPROVED', _('Approved')
        REJECTED = 'REJECTED', _('Rejected')

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='videos',
        limit_choices_to={'role': 'STUDENT'},
        db_column='student_id',
    )
    coach = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='coached_videos',
        limit_choices_to={'role': 'COACH'},
        db_column='coach_id',
    )

    title = models.CharField(_('title'), max_length=200)
    notes_to_coach = models.TextField(_('notes to coach'), blank=True, default='')

    video_file = models.FileField(_('video file'), upload_to=student_video_upload_to)
    original_filename = models.CharField(max_length=255, blank=True, default='')
    file_size = models.BigIntegerField(default=0)
    content_type = models.CharField(max_length=100, blank=True, default='')

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.UPLOADED,
        db_index=True,
    )
    coach_review_status = models.CharField(
        max_length=20,
        choices=CoachReviewStatus.choices,
        default=CoachReviewStatus.NOT_REQUIRED,
        db_index=True,
    )
    coach_reviewed_at = models.DateTimeField(null=True, blank=True)
    coach_review_comment = models.TextField(blank=True, default='')
    failure_reason = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'students_wrestlingvideo'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['student', '-created_at']),
            models.Index(fields=['coach', 'coach_review_status']),
            models.Index(fields=['status']),
        ]
        verbose_name = _('wrestling video')
        verbose_name_plural = _('wrestling videos')

    def __str__(self):
        return f"{self.title} ({self.status}) — student={self.student_id}"


class VideoAnalysis(models.Model):
    """AI analysis summary for one wrestling video (1:1)."""

    video = models.OneToOneField(
        WrestlingVideo,
        on_delete=models.CASCADE,
        related_name='analysis',
        db_column='video_id',
    )
    summary = models.TextField(blank=True, default='')
    match_analysis = models.JSONField(
        blank=True,
        default=dict,
        help_text=_('Top-level match summary (event, wrestlers, winner, finish, summary).'),
    )
    overall_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'students_videoanalysis'
        verbose_name = _('video analysis')
        verbose_name_plural = _('video analyses')

    def __str__(self):
        return f"Analysis for video={self.video_id}"


class AnalysisMovement(models.Model):
    """
    Per-frame AI analysis moment (table students_analysismovement).

    API exposes these as `frames` with rich technical_evaluation for blue/red wrestlers.
    """

    analysis = models.ForeignKey(
        VideoAnalysis,
        on_delete=models.CASCADE,
        related_name='movements',
        db_column='analysis_id',
    )
    # Legacy short label; prefer `phase` for new data.
    movement_name = models.CharField(max_length=200, blank=True, default='')
    phase = models.CharField(max_length=255, blank=True, default='')
    timestamp_seconds = models.FloatField(default=0)
    visual_description = models.TextField(blank=True, default='')
    technical_evaluation = models.JSONField(default=dict, blank=True)
    ai_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    ai_suggestion = models.TextField(blank=True, default='')  # legacy; prefer technical_evaluation
    coach_comment = models.TextField(blank=True, default='')
    coach_edited_at = models.DateTimeField(null=True, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    frame_image = models.ImageField(upload_to=analysis_frame_upload_to, blank=True, null=True)

    class Meta:
        db_table = 'students_analysismovement'
        ordering = ['sort_order', 'id']
        verbose_name = _('analysis frame')
        verbose_name_plural = _('analysis frames')

    def __str__(self):
        label = self.phase or self.movement_name or 'frame'
        return f"{label} @ {self.timestamp_seconds}s"
