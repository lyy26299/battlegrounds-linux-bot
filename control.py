"""Platform-independent gates, pacing and singleton lock."""
from pathlib import Path
import fcntl
from core import Phase


def stale(seconds, elapsed):
    return seconds is not None and seconds-elapsed < 4


def interval(phase, action=None):
    if action: return 3.0 if action.kind=='click' else 1.0
    return 4.0 if phase in (Phase.COMBAT,Phase.QUEUE,Phase.LOADING) else .6


def defer_transition_ocr(state, seconds_since_full):
    """Only defer known scene loading, with a five-second full-screen backstop."""
    return (isinstance(state,dict) and state.get('available') is True and
            state.get('scene_present') is True and 0 <= seconds_since_full < 5 and
            (state.get('m_transitioning') is True or state.get('m_sceneLoaded') is False))


class Lock:
    def __init__(self,path): self.path=Path(path); self.file=None
    def __enter__(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.file=self.path.open('a')
        try: fcntl.flock(self.file,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            self.file.close()
            raise RuntimeError('Another bot already owns this session')
        return self
    def __exit__(self,*args):
        self.file.close()
