import io
import sys

from ventilastation.app_loader import ensure_project_root_on_path
from ventilastation.director import director, ensure_runtime

ensure_runtime()
ensure_project_root_on_path()

from system.launcher.code import setup as setup_launcher

def setup():
    setup_launcher()

def main():
    setup()
    director.run()

if __name__ == '__main__':
    import machine
    try:
        director.sound_play(b"alecu.vyruss/shoot3")
        main()
    except Exception as e:
        # raise
        buf = io.StringIO()
        sys.print_exception(e, buf)
        director.report_traceback(buf.getvalue().encode("utf-8"))
        print(buf.getvalue())
        # machine.reset()
