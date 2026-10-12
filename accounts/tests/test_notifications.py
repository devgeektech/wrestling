from django.urls import reverse
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken
from unittest.mock import patch

from accounts.models import Notification, User
from accounts.throttles import AuthAnonRateThrottle, AuthUserRateThrottle
from common.notifications import notify_user, NotificationType


@override_settings(DEBUG=True)
class NotificationApiTests(APITestCase):
    def setUp(self):
        AuthAnonRateThrottle.rate = '10000/minute'
        AuthUserRateThrottle.rate = '10000/minute'

        self.coach = User.objects.create_user(
            email='coach-notify@example.com',
            password='CoachPassword123!',
            first_name='John',
            last_name='Coach',
            role=User.Roles.COACH,
        )
        self.student = User.objects.create_user(
            email='student-notify@example.com',
            password='StudentPassword123!',
            first_name='Rahul',
            last_name='Sharma',
            role=User.Roles.STUDENT,
            coach_assigned=self.coach,
        )
        self.list_url = reverse('notifications-list')
        self.read_all_url = reverse('notifications-read-all')

    def _auth(self, user):
        token = str(RefreshToken.for_user(user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    @patch('common.notifications.send_fcm_to_user', return_value=0)
    def test_notify_user_persists_for_coach_and_student(self, _mock_fcm):
        notify_user(
            self.coach,
            title='Video ready for review',
            body='A student submitted a video.',
            data={'type': NotificationType.VIDEO_PENDING_REVIEW, 'video_id': 1},
        )
        notify_user(
            self.student,
            title='Analysis complete',
            body='Your analysis is ready.',
            data={'type': NotificationType.ANALYSIS_READY, 'video_id': 1},
        )
        self.assertEqual(Notification.objects.filter(user=self.coach).count(), 1)
        self.assertEqual(Notification.objects.filter(user=self.student).count(), 1)

    @patch('common.notifications.send_fcm_to_user', return_value=0)
    def test_list_only_own_notifications(self, _mock_fcm):
        notify_user(
            self.coach,
            title='Coach note',
            body='For coach',
            data={'type': NotificationType.VIDEO_PENDING_REVIEW, 'video_id': 9},
        )
        notify_user(
            self.student,
            title='Student note',
            body='For student',
            data={'type': NotificationType.ANALYSIS_READY, 'video_id': 9},
        )

        self._auth(self.coach)
        coach_resp = self.client.get(self.list_url)
        self.assertEqual(coach_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(coach_resp.data['data']['unread_count'], 1)
        self.assertEqual(len(coach_resp.data['data']['results']), 1)
        self.assertEqual(coach_resp.data['data']['results'][0]['title'], 'Coach note')

        self._auth(self.student)
        student_resp = self.client.get(self.list_url)
        self.assertEqual(student_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(student_resp.data['data']['results']), 1)
        self.assertEqual(student_resp.data['data']['results'][0]['title'], 'Student note')

    @patch('common.notifications.send_fcm_to_user', return_value=0)
    def test_mark_one_and_all_read(self, _mock_fcm):
        notify_user(
            self.student,
            title='One',
            body='Body one',
            data={'type': NotificationType.ANALYSIS_READY, 'video_id': 1},
        )
        notify_user(
            self.student,
            title='Two',
            body='Body two',
            data={'type': NotificationType.VIDEO_APPROVED, 'video_id': 2},
        )
        notes = list(Notification.objects.filter(user=self.student).order_by('id'))
        self.assertEqual(len(notes), 2)

        self._auth(self.student)
        mark = self.client.post(
            reverse('notifications-mark-read', kwargs={'notification_id': notes[0].id})
        )
        self.assertEqual(mark.status_code, status.HTTP_200_OK)
        notes[0].refresh_from_db()
        self.assertTrue(notes[0].is_read)

        listed = self.client.get(self.list_url, {'unread_only': 'true'})
        self.assertEqual(listed.data['data']['unread_count'], 1)
        self.assertEqual(len(listed.data['data']['results']), 1)

        all_read = self.client.post(self.read_all_url)
        self.assertEqual(all_read.status_code, status.HTTP_200_OK)
        self.assertEqual(all_read.data['data']['updated'], 1)
        self.assertEqual(
            Notification.objects.filter(user=self.student, is_read=False).count(),
            0,
        )
