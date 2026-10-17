# Third-party components

Lilt uses unmodified CPython and the Qt for Python (PySide6 / Shiboken) shared libraries.

- CPython: Python Software Foundation License Version 2 and the additional notices in `licenses/PYTHON-LICENSE.txt`. Source and releases: https://www.python.org/downloads/source/.
- PySide6, Shiboken and the Qt libraries used by this application: available under the GNU Lesser General Public License version 3. The LGPL and its incorporated GPL text are provided in `licenses/`. Official source releases: https://download.qt.io/official_releases/QtForPython/ and https://download.qt.io/official_releases/qt/.

The package keeps these libraries separate under `_internal/`. Compatible modified or replacement library builds may be substituted there. Lilt does not modify those libraries or restrict debugging modifications to them. Library version information is available from the package self-test described in README.md.

Lilt's icons and interface assets are created for this project. Google and DeepL are remote services; their software and models are not bundled. Anki and AnkiConnect are installed separately by the user.

English definitions and phonetic text are retrieved from Free Dictionary API (https://dictionaryapi.dev/), separately from translation. Dictionary content is not bundled. Returned source URLs and license notices, including Wiktionary's supplied CC BY-SA attribution, are retained in the card's DictionarySource field and in exports.
