import os
import sys
import time

import pytest

from app.media.process import MediaError, run_process


@pytest.mark.skipif(os.name == "nt", reason="Production media workers use POSIX process groups")
def test_timeout_still_applies_when_parent_exits_but_descendant_holds_pipes():
    child = "import time; time.sleep(30)"
    parent = f"import subprocess,sys; subprocess.Popen([sys.executable, '-c', {child!r}])"
    started = time.monotonic()
    with pytest.raises(MediaError) as error:
        run_process([sys.executable, "-c", parent], timeout=.5)
    assert error.value.code == "process_timeout"
    assert time.monotonic() - started < 5
