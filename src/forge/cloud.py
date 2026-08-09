"""`forge cloud` — rented-compute readiness.

Deliberately read-only. Nothing here starts a machine or spends money; it
reports whether a provider *could* be dispatched to, and names exactly what is
missing when it could not. Job submission is a later, separately-reviewed
change — the gap between "plumbing exists" and "plumbing can spend money"
should be crossed on purpose.
"""
from forge import providers
from forge.output import emit

EXIT_OK = 0
EXIT_REFUSED = 2


def _human_preflight(r):
    head = f"{r['provider']:8} {'READY' if r['ok'] else 'NOT READY'}  {r['description']}"
    lines = [head]
    for env, source in sorted(r["resolved"].items()):
        lines.append(f"    ok       {env} (from {source})")
    for m in r["missing"]:
        via = f"; or {m['file']}" if m.get("file") else ""
        lines.append(f"    MISSING  {m['env']} — {m['description']}{via}")
    cli = r["cli"]
    if cli["name"]:
        if cli["ok"]:
            lines.append(f"    ok       {cli['name']} CLI at {cli['path']}")
        else:
            lines.append(f"    MISSING  {cli['name']} CLI — install: {cli['install']}")
    if r["gpus"]:
        lines.append(f"    gpus     {', '.join(r['gpus'])}")
    return "\n".join(lines)


def cmd_providers(args):
    rows = [{"provider": p.name, "description": p.description,
             "cli": p.cli, "gpus": list(p.gpus)}
            for p in providers.PROVIDERS.values()]
    human = "\n".join(f"{r['provider']:8} {r['description']}\n"
                      f"    gpus  {', '.join(r['gpus'])}" for r in rows)
    emit({"providers": rows}, args.as_json, human=human)
    return EXIT_OK


def cmd_preflight(args):
    if args.provider:
        try:
            selected = [providers.get(args.provider)]
        except providers.UnknownProvider as e:
            emit({"ok": False, "error": str(e)}, args.as_json)
            return EXIT_REFUSED
    else:
        selected = list(providers.PROVIDERS.values())

    results = [p.preflight() for p in selected]
    ok = all(r["ok"] for r in results)
    emit({"ok": ok, "results": results}, args.as_json,
         human="\n".join(_human_preflight(r) for r in results))
    # Not-ready is information, not failure: this command exists to be run
    # before the credentials arrive, so a red report still exits 0.
    return EXIT_OK


def register(subparsers):
    c = subparsers.add_parser("cloud", help="rented compute (Modal, Azure)")
    csub = c.add_subparsers(dest="cloud_command", required=True)

    lst = csub.add_parser("providers", help="list known providers")
    lst.set_defaults(func=cmd_providers)

    pre = csub.add_parser("preflight",
                          help="report which credentials/CLIs are present")
    pre.add_argument("--provider", default=None,
                     help="check one provider instead of all")
    pre.set_defaults(func=cmd_preflight)
