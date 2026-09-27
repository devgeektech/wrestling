"""Outbound email helpers for Wrestling Guide."""

from django.conf import settings
from django.core.mail import send_mail

from students.models import WrestlingVideo


def _from_email():
    return getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@wrestlingguide.local')


def send_student_welcome_email(user) -> None:
    """
    Welcome email after successful student registration.
    Failures are swallowed so registration is not blocked.
    """
    if not user or not getattr(user, 'email', None):
        return

    student_name = user.get_full_name() or user.email
    lines = [
        f"Hi {student_name},",
        "",
        "Welcome to Wrestling Guide!",
        "Your student account has been created successfully.",
        "You can now sign in and upload videos for coach review.",
        "",
        "— Wrestling Guide",
    ]
    send_mail(
        subject="Wrestling Guide – Welcome",
        message="\n".join(lines),
        from_email=_from_email(),
        recipient_list=[user.email],
        fail_silently=True,
    )


def send_video_review_ready_email(video: WrestlingVideo) -> None:
    """
    Notify the student that coach review is complete (approved or rejected).
    Failures are swallowed so the review API is not blocked.
    """
    student = video.student
    if not student or not student.email:
        return

    result = (
        'Approved'
        if video.status == WrestlingVideo.Status.APPROVED
        else 'Rejected'
    )
    student_name = student.get_full_name() or student.email
    comment = (video.coach_review_comment or '').strip()

    lines = [
        f"Hi {student_name},",
        "",
        f'Your video "{video.title}" has been reviewed by your coach.',
        f"Result: {result}.",
    ]
    if comment:
        lines.extend(["", f"Coach comment: {comment}"])
    lines.extend(
        [
            "",
            "Open the Wrestling Guide app to view details.",
            f"(Video id: {video.id})",
            "",
            "— Wrestling Guide",
        ]
    )

    send_mail(
        subject=f"Wrestling Guide – Video review ready ({result})",
        message="\n".join(lines),
        from_email=_from_email(),
        recipient_list=[student.email],
        fail_silently=True,
    )
