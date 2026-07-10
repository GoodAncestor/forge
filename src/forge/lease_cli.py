from forge import config
from forge.lease import FleetUnreachable, LeaseClient, LeaseRefused
from forge.output import emit

EXIT_OK, EXIT_REFUSED, EXIT_INFRA = 0, 2, 4


def register(subparsers):
    p = subparsers.add_parser("lease", help="fleet lease operations")
    sub = p.add_subparsers(dest="lease_command", required=True)

    acq = sub.add_parser("acquire")
    acq.add_argument("--target-type", required=True, choices=["node", "gpu", "pool"])
    acq.add_argument("--name", required=True)
    acq.add_argument("--mode", default="exclusive", choices=["exclusive", "floor"])
    acq.add_argument("--min-floor", type=int, default=None)
    acq.add_argument("--ttl", type=int, default=28800)
    acq.add_argument("--notes", default="")
    acq.add_argument("--holder", default=config.HOLDER)
    acq.set_defaults(func=cmd_acquire)

    ren = sub.add_parser("renew")
    ren.add_argument("--id", required=True)
    ren.add_argument("--ttl", type=int, default=28800)
    ren.set_defaults(func=cmd_renew)

    rel = sub.add_parser("release")
    rel.add_argument("--id", required=True)
    rel.set_defaults(func=cmd_release)

    st = sub.add_parser("status")
    st.set_defaults(func=cmd_status)


def _guard(args, fn):
    try:
        return fn()
    except LeaseRefused as e:
        emit({"ok": False, "error": str(e)}, args.as_json, human=f"REFUSED: {e}")
        return EXIT_REFUSED
    except FleetUnreachable as e:
        emit({"ok": False, "error": str(e)}, args.as_json, human=f"FLEET UNREACHABLE: {e}")
        return EXIT_INFRA


def cmd_acquire(args):
    def go():
        lease = LeaseClient().acquire(args.holder, args.target_type, args.name,
                                      mode=args.mode, ttl_sec=args.ttl,
                                      notes=args.notes, min_floor=args.min_floor)
        emit({"ok": True, "lease": lease}, args.as_json,
             human=f"lease {lease['id']} on {args.target_type}:{args.name} "
                   f"until {lease.get('expires')}")
        return EXIT_OK
    return _guard(args, go)


def cmd_renew(args):
    def go():
        lease = LeaseClient().renew(args.id, ttl_sec=args.ttl)
        emit({"ok": True, "lease": lease}, args.as_json,
             human=f"renewed {args.id} until {lease.get('expires')}")
        return EXIT_OK
    return _guard(args, go)


def cmd_release(args):
    def go():
        existed = LeaseClient().release(args.id)
        emit({"ok": True, "released": args.id, "existed": existed}, args.as_json,
             human=f"released {args.id} (existed={existed})")
        return EXIT_OK
    return _guard(args, go)


def cmd_status(args):
    def go():
        fleet = LeaseClient().fleet()
        nodes = [{"name": n.get("name"), "held_by": n.get("held_by"),
                  "serving": [s.get("model") for s in n.get("serving", [])]}
                 for n in fleet.get("nodes", [])]
        human = "\n".join(f"{n['name']:20} held_by={n['held_by']} serving={n['serving']}"
                          for n in nodes)
        emit({"nodes": nodes}, args.as_json, human=human)
        return EXIT_OK
    return _guard(args, go)
