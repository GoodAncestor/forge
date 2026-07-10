import argparse

from forge import __version__
from forge.output import emit

EXIT_OK = 0
EXIT_REFUSED = 2
EXIT_JOB = 3
EXIT_INFRA = 4


def build_parser():
    p = argparse.ArgumentParser(prog="forge", description="Good Ancestor model lab")
    p.add_argument("--json", action="store_true", dest="as_json",
                   help="machine-readable output")
    sub = p.add_subparsers(dest="command", required=True)

    ver = sub.add_parser("version", help="print version")
    ver.set_defaults(func=cmd_version)

    from forge import envs
    envs.register(sub)

    from forge import lease_cli
    lease_cli.register(sub)

    # later tasks append: from forge import data, run, envupdate
    # and call <module>.register(sub)
    return p


def cmd_version(args):
    emit({"name": "forge", "version": __version__}, args.as_json,
         human=f"forge {__version__}")
    return EXIT_OK


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
