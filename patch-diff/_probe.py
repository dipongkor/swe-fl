from sphinx.ext.autodoc.mock import mock
import sphinx.util.typing as T
with mock(['unknown']):
    import unknown
    C = unknown.secret.Class
    # _restify_py36 is the sibling renderer selected on Python 3.6 (supported by this Sphinx).
    for fn in ('_restify_py36','_restify_py37'):
        f=getattr(T,fn,None)
        if f is None: print(fn,'MISSING'); continue
        try: print(f"{fn}(C) = {f(C)!r}")
        except Exception as e: print(f"{fn}(C) EXC {type(e).__name__}: {e}")
    print("object __qualname__ =", repr(C.__qualname__))
