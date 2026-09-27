from rest_framework import serializers

from accounts.models import User
from common.media_urls import absolute_media_url


class CoachStudentListSerializer(serializers.ModelSerializer):
    """Assigned students for the logged-in coach."""

    profile_image = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            'id',
            'email',
            'first_name',
            'last_name',
            'phone',
            'profile_image',
            'role',
            'date_joined',
        )
        read_only_fields = fields

    def get_profile_image(self, obj):
        return absolute_media_url(obj.profile_image, self.context.get('request'))
