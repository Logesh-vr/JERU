import sys


def run():
    if len(sys.argv) > 1 and sys.argv[1] == "--light-helper":
        from .lighting import helper_main
        helper_main(sys.argv[2], sys.argv[3], int(sys.argv[4]))
    elif len(sys.argv) > 1 and sys.argv[1] == "--ai-worker":
        from .ai_worker import main
        main()
    elif len(sys.argv) > 2 and sys.argv[1] == "--self-check":
        from pathlib import Path
        from .diagnostics import run as check
        raise SystemExit(check(Path(sys.argv[2])))
    else:
        from .app import main
        raise SystemExit(main())


if __name__ == "__main__":
    run()
