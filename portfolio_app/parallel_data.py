"""Bounded parallel reads for independent, UI-free cached data loaders."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import current_thread

from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx


@contextmanager
def parallel_loads(loaders):
    """Keep workers inside the calling Streamlit run and join before returning.

    Loaders must only return data; rendering stays on the script thread.
    The context lets Streamlit's existing caches work inside worker threads.
    """
    context = get_script_run_ctx(suppress_warning=True)

    def initialize():
        if context is not None:
            add_script_run_ctx(current_thread(), context)

    with ThreadPoolExecutor(max_workers=min(4, max(1, len(loaders))),
                            initializer=initialize) as pool:
        yield {name: pool.submit(loader) for name, loader in loaders.items()}
