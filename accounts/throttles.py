from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class AuthAnonRateThrottle(AnonRateThrottle):
    scope = 'auth'


class AuthUserRateThrottle(UserRateThrottle):
    scope = 'auth'
