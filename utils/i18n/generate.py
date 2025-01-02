import glob
import babel
import polib

locales_to_pofiles = {}

# Parse pofiles so that we may
for path in glob.glob("locales/*/*/*.po"):
    segments = path.split("/")
    locale_name = segments[-3]
    locales_to_pofiles[locale_name] = polib.pofile(path)

# Sort by alphabetical order
locales_to_pofiles = dict(sorted(locales_to_pofiles.items()))

total_english_strings = len(locales_to_pofiles["en_US"])

lines = []

for locale, pofile in locales_to_pofiles.items():
    language_name = babel.Locale.parse(locale).get_display_name().capitalize()
    translation_percentage = int((len(pofile.translated_entries())/total_english_strings) * 100)

    lines.append(f""""{locale}": ("{language_name}", {translation_percentage})""")


with open("src/i18n/i18n_data.py", "w") as file:
    file.write("LOCALE_DATA = {\n")
    for line in lines:
        file.write(f"    {line},\n")
    file.write("}")
