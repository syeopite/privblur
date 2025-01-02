from typing import NamedTuple, Optional

class DefaultUserPreferences(NamedTuple):
    """NamedTuple that stores default user Preferences

    Attributes:
        language: user interface language
    """

    language: str = "en_US"
    theme: str = "auto"
    expand_posts: bool = False
