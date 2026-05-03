"""
CLI entrypoint and compatibility wrapper for baseline comparison.
"""

try:
    from adas.baseline.comparison import *  # noqa: F401,F403
    from adas.baseline.comparison import main
except ModuleNotFoundError:
    from baseline.comparison import *  # type: ignore # noqa: F401,F403
    from baseline.comparison import main  # type: ignore


if __name__ == "__main__":
    main()

