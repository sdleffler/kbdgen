import argparse
import yaml
import sys
from collections import OrderedDict

from . import __version__, KbdgenException, Parser, gen, logger

# TODO move into base?
generators = OrderedDict((
    ("win", gen.WindowsGenerator),
    ("osx", gen.OSXGenerator),
    ("x11", gen.XKBGenerator),
    ("svg", gen.SVGGenerator),
    ("android", gen.AndroidGenerator),
    ("ios", gen.AppleiOSGenerator),
))

def parse_args():
    def logging_type(string):
        n = {
            "critical": 50,
            "error": 40,
            "warning": 30,
            "info": 20,
            "debug": 10,
            "trace": 5
        }.get(string, None)

        if n is None:
            raise argparse.ArgumentTypeError("Invalid logging level.")
        return n

    p = argparse.ArgumentParser(prog="kbdgen")

    p.add_argument('--version', action='version',
                   version="%(prog)s " + __version__)
    p.add_argument('--logging', type=logging_type, default=20,
                   help="Logging level")
    p.add_argument('-K', '--key', nargs="*", dest='cfg_pairs',
                   help="Key-value overrides (eg -K target.thing.foo=42)")
    p.add_argument('-D', '--dry-run', action="store_true",
                   help="Don't build, just do sanity checks.")
    p.add_argument('-R', '--release', action='store_true',
                   help="Compile in 'release' mode (where necessary).")
    p.add_argument('-G', '--global', type=argparse.FileType('r'),
                   help="Override the global.yaml file")
    p.add_argument('-r', '--repo', help='Git repo to generate output from')
    p.add_argument('-b', '--branch', default='stable',
                   help='Git branch (default: stable)')
    p.add_argument('-t', '--target', required=True, choices=generators.keys(),
                   help="Target output.")
    p.add_argument('project', help="Keyboard generation project (yaml)",
                   type=argparse.FileType('r'),
                   default=sys.stdin)

    return p.parse_args()

def main():
    args = parse_args()
    logger.setLevel(args.logging)

    try:
        project = Parser().parse(args.project, args.cfg_pairs)
    except yaml.scanner.ScannerError as e:
        logger.critical("Error parsing project:\n%s %s" % (
                str(e.problem).strip(),
                str(e.problem_mark).strip()
            ))
        return 1
    except Exception as e:
        if logger.getEffectiveLevel() < 10:
            raise e
        logger.critical(e)
        return 1

    generator = generators.get(args.target, None)

    if generator is None:
        print("Error: '%s' is not a valid target." % args.target,
                file=sys.stderr)
        print("Valid targets: %s" % ", ".join(generators),
                file=sys.stderr)
        return 1

    x = generator(project, dict(args._get_kwargs()))

    try:
        x.generate()
    except KbdgenException as e:
        logger.error(e)
        return 1
    except KeyboardInterrupt:
        return 0

if __name__ == "__main__":
    sys.exit(main())
