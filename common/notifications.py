"""FCM push notification helpers."""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

_firebase_app = None


def upsert_device_token(user, token: str, platform: str = 'unknown'):
    """Create or reassign an FCM device token to `user`. Returns DeviceToken or None."""
    token = (token or '').strip()
    if not user or not token:
        return None

    from accounts.models import DeviceToken

    platform = (platform or DeviceToken.Platform.UNKNOWN).strip().lower()
    if platform not in {
        DeviceToken.Platform.IOS,
        DeviceToken.Platform.ANDROID,
        DeviceToken.Platform.UNKNOWN,
    }:
        platform = DeviceToken.Platform.UNKNOWN

    obj, _ = DeviceToken.objects.update_or_create(
        token=token,
        defaults={'user': user, 'platform': platform},
    )
    return obj


class NotificationType:
    VIDEO_PENDING_REVIEW = 'VIDEO_PENDING_REVIEW'
    ANALYSIS_READY = 'ANALYSIS_READY'
    VIDEO_APPROVED = 'VIDEO_APPROVED'


def _ensure_firebase():
    """Initialize firebase-admin once. Returns app or None if not configured."""
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app

    cred_path = (getattr(settings, 'FIREBASE_CREDENTIALS_FILE', None) or '').strip()
    if not cred_path:
        logger.debug('FCM skipped: FIREBASE_CREDENTIALS_FILE not set')
        return None

    try:
        import firebase_admin
        from firebase_admin import credentials

        if not firebase_admin._apps:
            cred = credentials.Certificate(cred_path)
            _firebase_app = firebase_admin.initialize_app(cred)
        else:
            _firebase_app = firebase_admin.get_app()
        return _firebase_app
    except Exception:
        logger.exception('FCM: failed to initialize Firebase')
        return None


def send_fcm_to_user(
    user,
    *,
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
) -> int:
    """
    Send a push to all device tokens for `user`.
    Returns number of successful sends. Never raises to callers.
    """
    if user is None:
        return 0

    from accounts.models import DeviceToken

    tokens = list(
        DeviceToken.objects.filter(user=user).values_list('token', flat=True)
    )
    if not tokens:
        return 0

    if _ensure_firebase() is None:
        logger.info(
            'FCM dry-run (no Firebase creds): user=%s title=%s tokens=%s',
            getattr(user, 'id', None),
            title,
            len(tokens),
        )
        return 0

    try:
        from firebase_admin import messaging
    except Exception:
        logger.exception('FCM: firebase_admin.messaging unavailable')
        return 0

    payload_data = {str(k): str(v) for k, v in (data or {}).items()}
    sent = 0
    invalid: list[str] = []

    for token in tokens:
        try:
            message = messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                data=payload_data,
                token=token,
            )
            messaging.send(message)
            sent += 1
        except Exception as exc:
            logger.warning('FCM send failed for token …%s: %s', token[-8:], exc)
            err = str(exc).lower()
            if any(
                s in err
                for s in (
                    'unregistered',
                    'invalid-registration-token',
                    'registration-token-not-registered',
                    'not-found',
                )
            ):
                invalid.append(token)

    if invalid:
        DeviceToken.objects.filter(token__in=invalid).delete()

    return sent


def notify_video_pending_review(video) -> None:
    """Coach: video ready for review. Student: analysis ready."""
    student = video.student
    coach = video.coach
    title_student = video.title or 'Your video'
    student_name = ''
    if student:
        student_name = student.get_full_name() or student.email

    if coach:
        send_fcm_to_user(
            coach,
            title='Video ready for review',
            body=f'{student_name or "A student"} submitted "{title_student}" for review.',
            data={
                'type': NotificationType.VIDEO_PENDING_REVIEW,
                'video_id': video.id,
            },
        )

    if student:
        send_fcm_to_user(
            student,
            title='Analysis complete',
            body=f'AI analysis for "{title_student}" is ready. Waiting for coach review.',
            data={
                'type': NotificationType.ANALYSIS_READY,
                'video_id': video.id,
            },
        )


def notify_video_approved(video) -> None:
    """Student: coach approved the video."""
    student = video.student
    if not student:
        return
    title_student = video.title or 'Your video'
    send_fcm_to_user(
        student,
        title='Video approved',
        body=f'Your coach approved "{title_student}".',
        data={
            'type': NotificationType.VIDEO_APPROVED,
            'video_id': video.id,
        },
    )
