from django.db import transaction
from django.db.models import Q

from accounts.models import Notification, User


@transaction.atomic
def hard_delete_student(user: User) -> None:
    """
    Permanently delete a student and related data.

    Cascades (via FK): device tokens, student notifications, videos, analysis, frames.
    Also removes coach inbox rows that reference that student's video IDs.
    """
    if user.role != User.Roles.STUDENT:
        raise ValueError('Only student accounts can be hard-deleted with this service.')

    video_ids = list(user.videos.values_list('id', flat=True))
    if video_ids:
        # Match int or string video_id in JSON (avoid broad/fragile __in quirks).
        video_q = Q()
        for vid in video_ids:
            video_q |= Q(data__video_id=vid) | Q(data__video_id=str(vid))
        Notification.objects.filter(video_q).delete()

    user.delete()
