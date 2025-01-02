import dataclasses
import urllib.parse

from .i18n import SUPPORTED_LANGUAGES

VERSION = 1

@dataclasses.dataclass
class UserPreferences:
    # See DefaultUserPreferences in config/user_preferences.py
    language: str
    theme: str

    expand_posts: bool

    # Tracks major revisions of the settings cookie
    # Only bump in case of breaking changes.
    version: int = 1

    def __post_init__(self):
        """Validates default user attribute values"""
        # Silently fallback when the language given is invalid
        # TODO raise error to the end-user and instance maintainer when necessary
        if self.language not in SUPPORTED_LANGUAGES:
            self.language = "en_US"

        if self.theme not in ("auto", "light", "dark"):
            self.theme = "auto"

    def replace_from_forms(self, request) -> 'UserPreferences':
        """Returns updated UserPreferences class from POST form data"""
        return self._replace(request, request.form)

    def replace_from_query(self, request) -> 'UserPreferences':
        """Returns updated UserPreferences class from request query args"""
        return self._replace(request, request.args)

    def replace_from_cookie(self, request) -> 'UserPreferences':
        """Returns updated UserPreferences class from the settings cookie"""
        request.ctx.invalid_settings_cookie = False

        try:
            if raw_prefs := request.cookies.get("settings"):
                raw_prefs = urllib.parse.parse_qs(raw_prefs)
                version = raw_prefs["version"][0]

                if int(version) == VERSION:
                    return self._replace(request, raw_prefs)
                else:
                    request.ctx.invalid_settings_cookie = True
        except (TypeError, KeyError, ValueError):
            request.ctx.invalid_settings_cookie = True
        
        return self

    def _replace(self, request, raw_new_prefs):
        """Returns updated UserPreferences class from values in raw_new_prefs"""
        # Get the field names of the UserPreferences dataclass
        fields = tuple(field.name for field in dataclasses.fields(UserPreferences))

        # Process Sanic's RequestParameters object to a dictionary
        # mapping the request argument to its first value.
        # Also skips over unknown fields.
        raw_new_prefs = {
            key: value[0] for key, value in raw_new_prefs.items() if key in fields
        }

        self.convert_value_to_python(raw_new_prefs)

        # TODO provide an error message to the end user when an unknown field is set,
        # or when an value is invalid.

        new_preferences = dataclasses.replace(self, **raw_new_prefs)
        request.ctx.language = new_preferences.language

        return new_preferences

    def to_url_encoded(self):
        """Encodes user preferences as URL query parameters

        Used to restore settings at /settings/restore
        """
        fields_dict = dataclasses.asdict(self)
        self.convert_value_to_string(fields_dict)

        return urllib.parse.urlencode(fields_dict)

    def convert_value_to_string(self, fields_dict):
        """Processes fields_dict attribute values to strings based on corresponding types

        Examines PEP 526 __annotations__ to do so.

        Example: Convert something with a Python bool value to on/off for HTML forms.
        """
        for attribute, type_ in self.__annotations__.items():
            if type_ is bool:
                fields_dict[attribute] = "on" if getattr(self, attribute) else "off"

    def convert_value_to_python(self, fields_dict):
        """Processes fields_dict attribute values to python datatypes based on corresponding types

        Examines PEP 526 __annotations__ to do so.

        Example: Convert "on"/"off" strings to Python bools
        """
        for attribute, type_ in self.__annotations__.items():
            if type_ is bool:
                fields_dict[attribute] = True if fields_dict[attribute] == "on" else False

    def construct_cookie(self, request):
        """Serializes user preferences into a cookie"""
        if request.app.ctx.PRIVIBLUR_CONFIG.deployment.https is True:
            secure = True
        else:
            secure = False

        cookie = {
            "key": "settings",
            "value": self.to_url_encoded(),
            "secure": secure,
            "max_age": 31540000
        }

        if request.app.ctx.PRIVIBLUR_CONFIG.deployment.domain:
            cookie["domain"] = request.app.ctx.PRIVIBLUR_CONFIG.deployment.domain

        return cookie
