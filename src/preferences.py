import datetime
import dataclasses
import urllib.parse

VERSION = 1

@dataclasses.dataclass
class UserPreferences:
    # See DefaultUserPreferences in config/user_preferences.py
    language: str

    # Tracks major revisions of the settings cookie
    # Only bump in case of breaking changes.
    version: int = 1

    def update_from_request(self, request):
        raw_new_prefs = request.form

        language = raw_new_prefs.get("language", request.app.ctx.PRIVIBLUR_CONFIG.default_user_preferences.language)
        if language not in request.app.ctx.SUPPORTED_LANGUAGES:
            language = request.app.ctx.PRIVIBLUR_CONFIG.default_user_preferences.language

        self.language = language
        request.ctx.language = self.language

    def to_forms(self):
        return urllib.parse.urlencode(dataclasses.asdict(self))

    def to_cookie(self, request):
        cookie = {
            "key": "settings",
            "value": self.to_forms(),
            "secure": request.app.ctx.PRIVIBLUR_CONFIG.deployment.https,
            "max_age": 31540000
        }

        if request.app.ctx.PRIVIBLUR_CONFIG.deployment.domain:
            cookie["domain"] = request.app.ctx.PRIVIBLUR_CONFIG.deployment.domain

        return cookie