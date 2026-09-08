from django.core.management.base import BaseCommand, CommandError
from accounts.models import User


class Command(BaseCommand):
    help = 'Seeds/creates the initial coach user account (login only — no public coach register).'

    DEFAULT_EMAIL = 'coach@yopmail.com'
    DEFAULT_PASSWORD = '!@#coach!@#'
    DEFAULT_FIRST_NAME = 'Coach'
    DEFAULT_LAST_NAME = 'Admin'

    def add_arguments(self, parser):
        parser.add_argument('--email', type=str, help='Coach email address', default=self.DEFAULT_EMAIL)
        parser.add_argument('--password', type=str, help='Coach password', default=self.DEFAULT_PASSWORD)
        parser.add_argument('--first-name', type=str, help='Coach first name', default=self.DEFAULT_FIRST_NAME)
        parser.add_argument('--last-name', type=str, help='Coach last name', default=self.DEFAULT_LAST_NAME)
        parser.add_argument('--phone', type=str, help='Coach phone number', default='')

    def handle(self, *args, **options):
        email = options.get('email')
        password = options.get('password')
        first_name = options.get('first_name')
        last_name = options.get('last_name')
        phone = options.get('phone')

        if not email:
            raise CommandError('Email address is required.')

        if User.objects.filter(email=email).exists():
            existing_user = User.objects.get(email=email)
            if existing_user.role != User.Roles.COACH:
                existing_user.role = User.Roles.COACH
                existing_user.save(update_fields=['role', 'updated_at'])
                self.stdout.write(self.style.SUCCESS(f'Updated user role to COACH for {email}.'))
            else:
                self.stdout.write(self.style.WARNING(f'Coach with email "{email}" already exists.'))
            return

        if not password:
            raise CommandError('Password is required.')

        try:
            coach = User.objects.create_coach(
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                phone=phone or None,
            )
            self.stdout.write(self.style.SUCCESS(f'Successfully created initial coach user: {coach.email}'))
        except Exception as e:
            raise CommandError(f'Failed to create coach user: {str(e)}')
