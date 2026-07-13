"""Forward hardware Python stdout to the line-based host protocol."""


class InfoWriter:
    """A text stream that emits complete lines as ``info`` host frames.

    ``print`` may call ``write`` separately for each argument, separator, and
    newline.  Buffering until a newline preserves one host message per printed
    line and keeps ordinary output from being interpreted as a host command.
    """

    def __init__(self, send):
        self._send = send
        self._pending = ""

    def _emit(self, line):
        # The command line stays ASCII; the payload preserves arbitrary Python
        # output (including spaces and UTF-8 text) exactly.
        data = line.encode("utf-8")
        self._send(b"info %d" % len(data), data)

    def write(self, text):
        if not isinstance(text, str):
            text = str(text)
        written = len(text)
        self._pending += text

        while True:
            newline = self._pending.find("\n")
            if newline < 0:
                break
            line = self._pending[:newline]
            self._pending = self._pending[newline + 1:]
            if line.endswith("\r"):
                line = line[:-1]
            self._emit(line)

        return written

    def flush(self):
        if self._pending:
            self._emit(self._pending)
            self._pending = ""

