import copy
import os.path
import shutil
import sys
import glob
from collections import defaultdict
from textwrap import dedent, indent

import pycountry
from lxml import etree
from lxml.etree import Element, SubElement

from .base import *
from .. import boolmap, get_logger, KbdgenException

logger = get_logger(__file__)

ANDROID_GLYPHS = {}

for api in (16, 19, 21, 23):
    with open(os.path.join(os.path.dirname(__file__), 'bin',
            "android-glyphs-api%s.bin" % api), 'rb') as f:
        ANDROID_GLYPHS[api] = boolmap.BoolMap(f.read())

class AndroidGenerator(Generator):
    REPO = "giella-ime"
    ANDROID_NS = "http://schemas.android.com/apk/res/android"
    NS = "http://schemas.android.com/apk/res-auto"

    def _element(self, *args, **kwargs):
        o = {}
        for k, v in kwargs.items():
            if k in ['keySpec', 'additionalMoreKeys', 'keyHintLabel'] and\
                    v in ['#', '@']:
                v = '\\' + v
            o["{%s}%s" % (self.NS, k)] = v
        return Element(*args, **o)

    def _android_subelement(self, *args, **kwargs):
        o = {}
        for k, v in kwargs.items():
            if k == 'keySpec' and v in ['#', '@']:
                v = '\\' + v
            o["{%s}%s" % (self.ANDROID_NS, k)] = v
        return SubElement(*args, **o)

    def _subelement(self, *args, **kwargs):
        o = {}
        for k, v in kwargs.items():
            if k == 'keySpec' and v in ['#', '@']:
                v = '\\' + v
            o["{%s}%s" % (self.NS, k)] = v
        return SubElement(*args, **o)

    def _tostring(self, tree):
        return etree.tostring(tree, pretty_print=True,
            xml_declaration=True, encoding='utf-8').decode()

    def generate(self, base='.', sdk_base='./sdk', ndk_base='./ndk'):
        sdk_base = os.getenv("ANDROID_HOME", sdk_base)
        ndk_base = os.getenv("NDK_HOME", ndk_base)

        if not self.sanity_checks(sdk_base, ndk_base):
            return

        if self.dry_run:
            logger.info("Dry run completed.")
            return

        self.get_source_tree(base, sdk_base, ndk_base)

        self.native_locale_workaround(base)

        styles = [
            ('phone', 'xml'),
            ('tablet', 'xml-sw600dp')
        ]

        files = []

        layouts = defaultdict(list)

        for name, kbd in self._project.layouts.items():

            files += [
                ('res/xml/keyboard_layout_set_%s.xml' % name, self.kbd_layout_set(kbd)),
                ('res/xml/kbd_%s.xml' % name, self.keyboard(kbd))
            ]

            for style, prefix in styles:
                self.gen_key_width(kbd, style)

                files.append(("res/%s/rows_%s.xml" % (prefix, name),
                    self.rows(kbd, style)))

                for row in self.rowkeys(kbd, style):
                    row = ("res/%s/%s" % (prefix, row[0]), row[1])
                    files.append(row)

            layouts[kbd.target("android").get("minimumSdk", None)].append(kbd)
            self.update_strings_xml(kbd, base)

        self.update_method_xmls(layouts, base)

        files.append(self.create_ant_properties(ndk_base, self.is_release))

        self.save_files(files, base)

        # Add zhfst files if found
        self.add_zhfst_files(base)

        self.update_dict_authority(base)

        self.update_localisation(base)

        self.generate_icons(base)

        self.build(base, self.is_release)

    def native_locale_workaround(self, base):
        for name, kbd in self._project.layouts.items():
            try:
                pycountry.languages.get(iso639_1_code=kbd.locale)
                continue
            except KeyError:
                pass

            locale = 'zz_%s' % kbd.locale
            kbd.display_names[locale] = kbd.display_names[kbd.locale]
            kbd._tree['locale'] = locale

            self.update_locale_exception(kbd, base)

    def sanity_checks(self, sdk_base, ndk_base):
        sane = True

        if not os.path.exists(os.path.join(
            os.path.abspath(sdk_base), 'tools', 'android')):
            raise MissingApplicationException(
                    "Error: Could not find the Android SDK. " +\
                    "Ensure your environment is configured correctly, " +\
                    "specifically the ANDROID_HOME env variable.")

        if not os.path.exists(os.path.abspath(ndk_base)):
            raise MissingApplicationException(
                    "Error: Could not find the Android NDK. " +\
                    "Ensure your environment is configured correctly, " +\
                    "specifically the NDK_HOME env variable.")

        pid = self._project.target('android').get('packageId')
        if pid is None:
            sane = False
            logger.error("No package ID provided for Android target.")

        for name, kbd in self._project.layouts.items():
            dropped_locales = []

            for dn_locale in kbd.display_names:
                if dn_locale in ['zz', kbd.locale]:
                    continue
                try:
                    pycountry.languages.get(iso639_1_code=dn_locale)
                except KeyError:
                    logger.warning(("[%s] '%s' is not a supported locale. " +\
                          "You should provide the code in ISO 639-1 " +\
                          "format, if possible. Pruning from project.") % (name, dn_locale))
                    dropped_locales.append(dn_locale)

            for locale in dropped_locales:
                logger.debug("Pruning locale '%s'" % locale)
                del kbd.display_names[locale]

            for mode, rows in kbd.modes.items():
                for n, row in enumerate(rows):
                    if len(row) > 11:
                        logger.warning(("[%s] row %s has %s keys. It is " +\
                               "recommended to have less than 12 keys per " +\
                               "row.") % (name, n+1, len(row)))

            self.detect_unavailable_glyphs_long_press(kbd, 16)
            self.detect_unavailable_glyphs_long_press(kbd, 19)
            self.detect_unavailable_glyphs_long_press(kbd, 21)
            self.detect_unavailable_glyphs_long_press(kbd, 23)
        return sane

    def _update_dict_auth_xml(self, auth, base):
        path = os.path.join(base, 'deps', self.REPO, 'res/values/dictionary-pack.xml')
        with open(path) as f:
            tree = etree.parse(f)

        nodes = tree.xpath("string[@name='authority']")
        if len(nodes) == 0:
            logger.error("No authority string found in XML!")
            return

        nodes[0].text = auth

        with open(path, 'w') as f:
            f.write(self._tostring(tree))

    def _update_dict_auth_java(self, auth, base):
        # ಠ_ಠ
        target = "com.android.inputmethod.dictionarypack.aosp"

        # (╯°□°）╯︵ ┻━┻
        src_path = "src/com/android/inputmethod/dictionarypack/DictionaryPackConstants.java"
        path = os.path.join(base, 'deps', self.REPO, src_path)

        # (┛◉Д◉)┛彡┻━┻
        with open(path) as f:
            o = f.read().replace(target, auth)
        with open(path, 'w') as f:
            f.write(o)

    def update_dict_authority(self, base):
        auth = "%s.dictionarypack" % self._project.target('android')['packageId']
        logger.info("Updating dict authority string to '%s'..." % auth)

        self._update_dict_auth_xml(auth, base)
        self._update_dict_auth_java(auth, base)

    def add_zhfst_files(self, build_dir):
        nm = 'assets/dicts'
        dict_path = os.path.join(build_dir, 'deps', self.REPO, nm)
        if os.path.exists(dict_path):
            shutil.rmtree(dict_path)
        os.makedirs(dict_path, exist_ok=True)

        files = glob.glob(os.path.join(self._project.path, '*.zhfst'))
        if len(files) == 0:
            logger.warning("No ZHFST files found.")
            return

        path = os.path.join(build_dir, 'deps', self.REPO, 'res',
            'xml', 'spellchecker.xml')

        with open(path) as f:
            tree = etree.parse(f)
        root = tree.getroot()
        # Empty the file
        for child in root:
            root.remove(child)

        for fn in files:
            bfn = os.path.basename(fn)
            logger.info("Adding '%s' to '%s'…" % (bfn, nm))
            shutil.copyfile(fn, os.path.join(dict_path, bfn))

            lang, _ = os.path.splitext(os.path.basename(fn))
            try:
                # Will exception on failure
                pycountry.languages.get(iso639_1_code=lang)
            except KeyError:
                lang = "zz_%s" % lang.upper()

            self._android_subelement(root, 'subtype',
                label="@string/subtype_generic",
                subtypeLocale=lang)

        with open(path, 'w') as f:
            f.write(self._tostring(tree))

    def _upd_locale(self, d, values):
        logger.info("Updating localisation for %s..." % d)

        fn = os.path.join(d, "strings-appname.xml")
        node = None

        if os.path.exists(fn):
            with open(fn) as f:
                tree = etree.parse(f)
            nodes = tree.xpath("string[@name='english_ime_name']")
            if len(nodes) > 0:
                node = nodes[0]
        else:
            tree = etree.XML("<resources/>")

        if node is None:
            node = SubElement(tree, 'string', name="english_ime_name")

        node.text = values['name'].replace("'", r"\'")

        with open(fn, 'w') as f:
            f.write(self._tostring(tree))

    def update_localisation(self, base):
        res_dir = os.path.join(base, 'deps', self.REPO, 'res')

        self._upd_locale(os.path.join(res_dir, "values"),
            self._project.locales['en'])

        for locale, values in self._project.locales.items():
            d = os.path.join(res_dir, "values-%s" % locale)
            if os.path.isdir(d):
                self._upd_locale(d, values)

    def generate_icons(self, base):
        icon = self._project.icon('android')
        if icon is None:
            logger.warning("no icon supplied!")
            return

        res_dir = os.path.join(base, 'deps', self.REPO, 'res')

        cmd_tmpl = "convert -resize %dx%d %s %s"

        for suffix, dimen in (
                ('mdpi', 48),
                ('hdpi', 72),
                ('xhdpi', 96),
                ('xxhdpi', 144),
                ('xxxhdpi', 192)):
            mipmap_dir = "drawable-%s" % suffix
            cmd = cmd_tmpl % (dimen, dimen, icon, os.path.join(
                res_dir, mipmap_dir, "ic_launcher_keyboard.png"))

            logger.info("Creating '%s' at size %dx%d" % (mipmap_dir, dimen, dimen))
            process = subprocess.Popen(cmd, shell=True,
                    stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            out, err = process.communicate()
            if process.returncode != 0:
                logger.error(err.decode())
                logger.error("Application ended with error code %s." % process.returncode)
                # TODO throw exception instead.
                sys.exit(process.returncode)


    def build(self, base, release_mode=True):
        # TODO normal build
        logger.info("Building...")
        process = subprocess.Popen(['ant', 'release' if release_mode else 'debug'],
                    cwd=os.path.join(base, 'deps', self.REPO))
        process.wait()

        if process.returncode != 0:
            logger.error("Application ended with error code %s." % process.returncode)
            sys.exit(process.returncode)

        if not release_mode:
            fn = self._project.internal_name + "-debug.apk"
        else:
            fn = self._project.internal_name + "-release.apk"
            # TODO other release shi
        path = os.path.join(base, 'deps', self.REPO, 'bin')

        logger.info("Copying '%s' to build/ directory..." % fn)
        os.makedirs(os.path.join(base, 'build'), exist_ok=True)
        shutil.copy(os.path.join(path, fn), os.path.join(base, 'build'))

        logger.info("Done!")

    def _str_xml(self, val_dir, name, subtype):
        os.makedirs(val_dir, exist_ok=True)
        fn = os.path.join(val_dir, 'strings.xml')
        logger.info("Updating '%s'..." % fn)

        if not os.path.exists(fn):
            root = etree.XML("<resources/>")
        else:
            with open(fn) as f:
                root = etree.parse(f).getroot()

        SubElement(root,
            "string",
            name="subtype_%s" % subtype)\
            .text = name

        with open(fn, 'w') as f:
            f.write(self._tostring(root))

    def update_locale_exception(self, kbd, base):
        res_dir = os.path.join(base, 'deps', self.REPO, 'res')
        fn = os.path.join(res_dir, 'values', 'donottranslate.xml')

        logger.info("Adding '%s' to '%s'..." % (kbd.locale, fn))

        with open(fn) as f:
            tree = etree.parse(f)

        # Add to exception keys
        node = tree.xpath("string-array[@name='subtype_locale_exception_keys']")[0]
        SubElement(node, 'item').text = kbd.locale

        node = tree.xpath("string-array[@name='subtype_locale_displayed_in_root_locale']")[0]
        SubElement(node, 'item').text = kbd.locale

        SubElement(tree.getroot(), 'string', name="subtype_in_root_locale_%s" % kbd.locale).text = kbd.display_names[kbd.locale]

        with open(fn, 'w') as f:
            f.write(self._tostring(tree.getroot()))

    def update_strings_xml(self, kbd, base):
        # TODO sanity check for non-existence directories
        # TODO run this only once preferably
        res_dir = os.path.join(base, 'deps', self.REPO, 'res')

        for locale, name in kbd.display_names.items():
            try:
                pycountry.languages.get(iso639_1_code=locale)
            except:
                continue

            if locale == "en":
                val_dir = os.path.join(res_dir, 'values')
            else:
                val_dir = os.path.join(res_dir, 'values-%s' % locale)
            self._str_xml(val_dir, name, kbd.internal_name)


    def gen_method_xml(self, kbds, tree):
        root = tree.getroot()

        for kbd in kbds:
            self._android_subelement(root, 'subtype',
                icon="@drawable/ic_ime_switcher_dark",
                label="@string/subtype_%s" % kbd.internal_name,
                imeSubtypeLocale=kbd.locale,
                imeSubtypeMode="keyboard",
                imeSubtypeExtraValue="KeyboardLayoutSet=%s,AsciiCapable,EmojiCapable" % kbd.internal_name)

        return self._tostring(tree)

    def update_method_xmls(self, layouts, base):
        # None because no API version specified (nor needed)
        base_layouts = layouts[None]
        del layouts[None]

        logger.info("Updating 'res/xml/method.xml'...")
        path = os.path.join(base, 'deps', self.REPO, 'res', '%s')
        fn = os.path.join(path, 'method.xml')

        with open(fn % 'xml') as f:
            tree = etree.parse(f)
            root = tree.getroot()
            # Empty the method.xml file
            for child in root:
                root.remove(child)
        with open(fn % 'xml', 'w') as f:
            f.write(self.gen_method_xml(base_layouts, tree))

        for kl, vl in reversed(sorted(layouts.items())):
            for kr, vr in layouts.items():
                if kl >= kr:
                    continue
                layouts[kr] = vl + vr

        for api_ver, kbds in layouts.items():
            xmlv = "xml-v%s" % api_ver
            logger.info("Updating 'res/%s/method.xml'..." % xmlv)
            os.makedirs(path % xmlv, exist_ok=True)
            with open(fn % xmlv, 'w') as f:
                f.write(self.gen_method_xml(kbds, copy.deepcopy(tree)))

    def save_files(self, files, base):
        fn = os.path.join(base, 'deps', self.REPO)
        for k, v in files:
            with open(os.path.join(fn, k), 'w') as f:
                logger.info("Creating '%s'..." % k)
                f.write(v)

    def get_source_tree(self, base, sdk_base, ndk_base):
        deps_dir = os.path.join(base, 'deps')
        os.makedirs(deps_dir, exist_ok=True)

        logger.info("Preparing dependencies...")

        repo_dir = os.path.join(deps_dir, self.REPO)

        if os.path.isdir(repo_dir):
            git_update(repo_dir, self.branch, base, logger=logger.info)
        else:
            git_clone(self.repo, repo_dir, self.branch, base, logger=logger.info)

        logger.info("Create Android project...")

        cmd = "%s update project -n %s -t android-23 -p ." % (
            os.path.join(os.path.abspath(sdk_base), 'tools/android'),
            self._project.internal_name)
        process = subprocess.Popen(cmd, cwd=os.path.join(deps_dir, self.REPO),
                shell=True)
        process.wait()
        if process.returncode != 0:
            raise KbdgenException("Application ended with error code %s." % process.returncode)

        #rules_fn = os.path.join(deps_dir, self.REPO, 'custom_rules.xml')
        #with open(rules_fn) as f:
        #    x = f.read()
        #with open(rules_fn, 'w') as f:
        #    f.write(x.replace('GiellaIME', self._project.internal_name))

    def create_ant_properties(self, ndk_dir, release_mode=False):
        o = OrderedDict()

        if release_mode:
            o['key.store'] = os.path.abspath(self._project.target('android')['keyStore'])
            o['key.alias'] = self._project.target('android')['keyAlias']

        # We do this here because Android Tools doesn't handle it.
        o['ndk.dir'] = ndk_dir
        o['package.name'] = self._project.target('android')['packageId']
        o['version.code'] = self._project.build
        o['version.name'] = self._project.version
        o['java.source'] = 7
        o['java.target'] = 7

        data = "\n".join(["%s=%s" % (k, v) for k, v in o.items()])

        return ('ant.properties', data)

    def kbd_layout_set(self, kbd):
        out = Element("KeyboardLayoutSet", nsmap={"latin": self.NS})

        kbd_str = "@xml/kbd_%s" % kbd.internal_name

        self._subelement(out, "Element", elementName="alphabet",
            elementKeyboard=kbd_str,
            enableProximityCharsCorrection="true")

        for name, kbd_str in (
            ("alphabetAutomaticShifted", kbd_str),
            ("alphabetManualShifted", kbd_str),
            ("alphabetShiftLocked", kbd_str),
            ("alphabetShiftLockShifted", kbd_str),
            ("symbols", "@xml/kbd_symbols"),
            ("symbolsShifted", "@xml/kbd_symbols_shift"),
            ("phone", "@xml/kbd_phone"),
            ("phoneSymbols", "@xml/kbd_phone_symbols"),
            ("number", "@xml/kbd_number")
        ):
            self._subelement(out, "Element", elementName=name, elementKeyboard=kbd_str)

        return self._tostring(out)

    def row_has_special_keys(self, kbd, n, style):
        for key, action in kbd.get_actions(style).items():
            if action.row == n:
                return True
        return False

    def rows(self, kbd, style):
        out = Element("merge", nsmap={"latin": self.NS})

        self._subelement(out, "include", keyboardLayout="@xml/key_styles_common")

        for n, values in enumerate(kbd.modes['mobile-default']):
            n += 1

            row = self._subelement(out, "Row")
            include = self._subelement(row, "include", keyboardLayout="@xml/rowkeys_%s%s" % (
                kbd.internal_name, n))

            if not self.row_has_special_keys(kbd, n, style):
                self._attrib(include, keyWidth='%.2f%%p' % (100 / len(values)))
            else:
                self._attrib(include, keyWidth='%.2f%%p' % self.key_width)

        # All the fun buttons!
        self._subelement(out, "include", keyboardLayout="@xml/row_qwerty4")

        return self._tostring(out)

    def gen_key_width(self, kbd, style):
        m = 0
        for row in kbd.modes['mobile-default']:
            r = len(row)
            if r > m:
               m = r

        vals = {
            "phone": 95,
            "tablet": 90
        }

        self.key_width = (vals[style] / m)

    def keyboard(self, kbd, **kwargs):
        out = Element("Keyboard", nsmap={"latin": self.NS})

        self._attrib(out, **kwargs)

        self._subelement(out, "include", keyboardLayout="@xml/rows_%s" % kbd.internal_name)

        return self._tostring(out)

    def rowkeys(self, kbd, style):
        # TODO check that lengths of both modes are the same
        for n in range(1, len(kbd.modes['mobile-default'])+1):
            merge = Element('merge', nsmap={"latin": self.NS})
            switch = self._subelement(merge, 'switch')

            case = self._subelement(switch, 'case',
                keyboardLayoutSetElement="alphabetManualShifted|alphabetShiftLocked|" +
                                         "alphabetShiftLockShifted")

            self.add_rows(kbd, n, kbd.modes['mobile-shift'][n-1], style, case)

            default = self._subelement(switch, 'default')

            self.add_rows(kbd, n, kbd.modes['mobile-default'][n-1], style, default)

            yield ('rowkeys_%s%s.xml' % (kbd.internal_name, n), self._tostring(merge))

    def _attrib(self, node, **kwargs):
        for k, v in kwargs.items():
            node.attrib["{%s}%s" % (self.NS, k)] = v

    def add_button_type(self, key, action, row, tree, is_start):
        node = self._element("Key")
        width = action.width

        if width == "fill":
            if is_start:
                width = "%.2f%%" % ((100 - (self.key_width * len(row))) / 2)
            else:
                width = "fillRight"
        elif width.endswith("%"):
            width += 'p'

        if key == "backspace":
            self._attrib(node, keyStyle="deleteKeyStyle")
        if key == "enter":
            self._attrib(node, keyStyle="enterKeyStyle")
        if key == "shift":
            self._attrib(node, keyStyle="shiftKeyStyle")
        self._attrib(node, keyWidth=width)

        tree.append(node)

    def add_special_buttons(self, kbd, n, style, row, tree, is_start):
        side = "left" if is_start else "right"

        for key, action in kbd.get_actions(style).items():
            if action.row == n and action.position in [side, 'both']:
                self.add_button_type(key, action, row, tree, is_start)

    def add_rows(self, kbd, n, values, style, out):
        i = 1

        self.add_special_buttons(kbd, n, style, values, out, True)

        for key in values:
            more_keys = kbd.get_longpress(key)

            node = self._subelement(out, "Key", keySpec=key)
            if n == 1:
                if i > 0 and i <= 10:
                    if i == 10:
                        i = 0
                    self._attrib(node,
                            keyHintLabel=str(i),
                            additionalMoreKeys=str(i))
                    if i > 0:
                        i += 1
                elif more_keys is not None:
                    self._attrib(node, keyHintLabel=more_keys[0])

            elif more_keys is not None:
                self._attrib(node, keyHintLabel=more_keys[0])

            if more_keys is not None:
                self._attrib(node, moreKeys=','.join(more_keys))

        self.add_special_buttons(kbd, n, style, values, out, False)

    def detect_unavailable_glyphs_long_press(self, layout, api_ver):
        glyphs = ANDROID_GLYPHS.get(api_ver, None)
        if glyphs is None:
            logger.warning(("no glyphs file found for API %s! Can't detect " +
                  "missing characters from Android font!") % api_ver)
            return

        for vals in layout.longpress.values():
            for v in vals:
                for c in v:
                    if glyphs[ord(c)] is False:
                        logger.warning(("[%s] '%s' (codepoint: U+%04X) " +
                                       "is not supported by API %s!") % (
                            layout.internal_name,
                            c, ord(c), api_ver))

    def detect_unavailable_glyphs_keys(self, key, api_ver):
        glyphs = ANDROID_GLYPHS.get(api_ver, None)
        if glyphs is None:
            logger.warning("no glyphs file found for API %s! Can't detect " +
                  "missing characters from Android font!" % api_ver)
            return
