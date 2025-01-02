import sys
import gettext
import typing

import sanic

from .i18n_data import LOCALE_DATA


class Language:
    """Stores metadata about supported translations"""
    def __init__(self, locale, gettext_instance,) -> None:
        self.locale = locale

        self.priviblur_translations = gettext_instance

        self.name, self.translation_percentage = LOCALE_DATA[locale]

SUPPORTED_LANGUAGES = [
    "en_US", "cs_CZ", "fr", "ja", "uk", "zh_Hans", "zh_Hant", "es"
]

SUPPORTED_LANGUAGES.sort()


def initialize_locales() -> typing.Mapping[str, Language]:
    """Initializes locales into GNUTranslations instances"""
    try:
        # Initialize english locale first so that we may use it as a fallback

        priviblur_english_instance = gettext.translation("priviblur", localedir="locales", languages=("en_US",))

        languages = {
            "en_US": Language("en_US", priviblur_english_instance)
        }

        for locale in SUPPORTED_LANGUAGES:
            if locale == "en_US":
                continue

            instance = gettext.translation("priviblur", localedir="locales", languages=(locale,))
            instance.add_fallback(priviblur_english_instance)

            languages[locale] = Language(locale, instance)
    except FileNotFoundError as e:
        print(
            'Error: Unable to find locale files. '
            'Did you forget to compile them?'
        )

        sys.exit()
    except Exception as e:
        raise e

    return languages


def translate(language : str, id : str, number : int | float | None = None,
              substitution : str | dict | None = None) -> str:
    app = sanic.Sanic.get_app("Priviblur")

    gettext_instance = app.ctx.LANGUAGES[language].priviblur_translations

    if number is not None:
        translated = gettext_instance.ngettext(id, f"{id}_plural", number)
    else:
        translated = gettext_instance.gettext(id)

    if isinstance(substitution, str):
        translated = translated.format(substitution)
    elif isinstance(substitution, dict):
        translated = translated.format(**substitution)

    return translated
