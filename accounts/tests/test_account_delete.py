from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken
from unittest.mock import patch

from accounts.models import DeviceToken, Notification, User
from accounts.throttles import AuthAnonRateThrottle, AuthUserRateThrottle
from common.notifications import NotificationType, notify_user
from students.models import WrestlingVideo


@override_settings(DEBUG=True)
class AccountDeleteTests(APITestCase):
    def setUp(self):
        AuthAnonRateThrottle.rate = '10000/minute'
        AuthUserRateThrottle.rate = '10000/minute'

        self.coach = User.objects.create_user(
            email='coach-delete@example.com',
            password='CoachPassword123!',
            first_name='John',
            last_name='Coach',
            role=User.Roles.COACH,
        )
        self.student = User.objects.create_user(
            email='student-delete@example.com',
            password='StudentPassword123!',
            first_name='Rahul',
            last_name='Sharma',
            role=User.Roles.STUDENT,
            coach_assigned=self.coach,
        )
        self.url = reverse('account-delete')

    def _auth(self, user):
        token = str(RefreshToken.for_user(user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def _make_video(self, student, coach, title='Clip'):
        return WrestlingVideo.objects.create(
            student=student,
            coach=coach,
            title=title,
            video_file=SimpleUploadedFile('clip.mp4', b'fake-video', content_type='video/mp4'),
            original_filename='clip.mp4',
            file_size=10,
            content_type='video/mp4',
        )

    def test_unauthenticated_forbidden(self):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_coach_forbidden(self):
        self._auth(self.coach)
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(User.objects.filter(id=self.coach.id).exists())

    @patch('common.notifications.send_fcm_to_user', return_value=0)
    def test_student_hard_delete_removes_related_data(self, _mock_fcm):
        video = self._make_video(self.student, self.coach)
        DeviceToken.objects.create(
            user=self.student,
            token='student-fcm-delete-1',
            platform=DeviceToken.Platform.ANDROID,
        )
        notify_user(
            self.coach,
            title='Video ready for review',
            body='Pending',
            data={'type': NotificationType.VIDEO_PENDING_REVIEW, 'video_id': video.id},
        )
        notify_user(
            self.student,
            title='Analysis complete',
            body='Ready',
            data={'type': NotificationType.ANALYSIS_READY, 'video_id': video.id},
        )
        # Unrelated coach notification must survive.
        notify_user(
            self.coach,
            title='Other video',
            body='Keep me',
            data={'type': NotificationType.VIDEO_PENDING_REVIEW, 'video_id': 99999},
        )

        student_id = self.student.id
        video_id = video.id
        self._auth(self.student)
        response = self.client.delete(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertFalse(User.objects.filter(id=student_id).exists())
        self.assertFalse(WrestlingVideo.objects.filter(id=video_id).exists())
        self.assertFalse(DeviceToken.objects.filter(user_id=student_id).exists())
        remaining = list(Notification.objects.filter(user=self.coach))
        self.assertEqual(len(remaining), 1)
        self.assertEqual(str(remaining[0].data.get('video_id')), '99999')
        self.assertFalse(Notification.objects.filter(user_id=student_id).exists())
        self.assertTrue(User.objects.filter(id=self.coach.id).exists())

    @patch('common.notifications.send_fcm_to_user', return_value=0)
    def test_email_reusable_after_delete(self, _mock_fcm):
        email = self.student.email
        self._auth(self.student)
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        again = User.objects.create_user(
            email=email,
            password='NewStudentPassword123!',
            first_name='Rahul',
            last_name='Again',
            role=User.Roles.STUDENT,
            coach_assigned=self.coach,
        )
        self.assertEqual(again.email, email)
