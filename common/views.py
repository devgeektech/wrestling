from django.views.generic import TemplateView


class TermsOfServiceView(TemplateView):
    template_name = 'legal/terms.html'


class PrivacyPolicyView(TemplateView):
    template_name = 'legal/privacy.html'
