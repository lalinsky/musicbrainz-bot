import sys
import os

class PIDFile(object):

    def __init__(self, path):
        self.path = path
        self.pid = os.getpid()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.release()

    def _create(self):
        # Create a new PID file, failing if the file already exists
        fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0644)
        try:
            os.write(fd, "%d\n" % (self.pid,))
        finally:
            os.close(fd)

    def _read(self):
        # Read an existing PID file
        try:
            return int(open(self.path).read().strip())
        except ValueError:
            return 0

    def acquire(self):
        # Acquire a lock on the PID file, trying to remove stale locks for
        # processes that crashed
        try:
            self._create()
        except OSError, e:
            if e.errno != 17: # File exists
                raise
            old_pid = self._read()
            if os.path.exists("/proc/%s" % (old_pid,)):
                raise Exception("already running with PID %s" % (old_pid,))
            # Break the lock and try to create it again, this starts a race
            # which we might not win, but that's fine because it will raise
            # exception and only one script will continue
            print >>sys.stderr, "removing stale lock for PID %s" % (old_pid,)
            self.release()
            self.acquire()

    def release(self):
        # Release the lock on the PID file
        try:
            os.unlink(self.path)
        except OSError, e:
            if e.errno != 2: # No such file or directory
                raise

