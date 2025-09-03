
from django.conf import settings

class CookieConsentMiddleware:
    """
    Entfernt oder verhindert Cookies, solange der User nicht zugestimmt hat.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        consent = request.COOKIES.get("cookies_accepted")
        if consent != "true":
            # CSRF-Cookie löschen
            response.delete_cookie("csrftoken", path="/")
            # Session-Cookie löschen
            response.delete_cookie(getattr(settings, "SESSION_COOKIE_NAME", "sessionid"), path="/")

        return response
