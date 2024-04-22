"""
Uninstall the packages used for doctests. Run with `python -m doctest lazy.py`

>>> pip(["uninstall", "-qqy", "fuzzywuzzy", "regex", "msgpack", "itk", "itk-fpfh"])
"""

import json
import subprocess
import sys
import tempfile
import types


import importlib.abc
import importlib.machinery
import importlib.resources
import importlib.util


def pip(args):
    subprocess.run(["pip"] + args, stdout=subprocess.PIPE)


EXTRA_PIP_ARGS = [
    "--quiet",
]


class LazyImportGroup:
    """
    A context manager which temporarily defers `import` statements till first usage, installing dependencies.

    >>> with LazyImportGroup('pak:requirements.txt'):
    ...     import pak

    `import pak` here creates a dummy `VeryLazyModule` which defers execution till first attribute access.

    >>> pak.dopak()  # lazily triggers `pip install -r requirements.txt` and `import pak`
    installing fuzzywuzzy==0.18.0 (Fuzzy string matching in python)
    installing msgpack==1.0.8 (MessagePack serializer)
    hello fuzzywuzzy

    The requirements file is specified in the form `package:resource` where `package` and `resource` are passed to
    `importlib.resources` to locate the resource. For example `pak:requirements.txt` finds the `requirements.txt`
    resource in the `pak` package.

    All imports within a LazyImportGroup share the same requirements, and installation is only triggered once.

    >>> with LazyImportGroup('pak:requirements.txt'):
    ...     import pak
    ...     import pak.bar

    >>> pak.dopak()  # triggers pip install -r requirements.txt
    hello fuzzywuzzy

    >>> pak.bar.dobar()  # module is already loaded
    hello msgpack

    Raw `import` of a lazily-imported module outside the context manager is illegal when the requirements are not
    guaranteed to be satisfied. This is explicitly disabled, so such raw imports will produce `ImportError`, even
    if the dependencies happen to be met in the particular environment. This hels developers catch the error that
    a package might be installed in their environment, but not during first usage on a user's environment.

    Once some module in the import group is resolved, all the dependencies are installed together and the other
    modules in the group are unlocked. This means lazily-imported modules can safely contain raw relative imports
    and top-level dependency imports, since the group dependencies are guaranteed to be met.

    >>> with LazyImportGroup('nspak:requirements.txt'):
    ...     import nspak.foo

    >>> import nspak  # ImportError; explicitly disabled
    Traceback (most recent call last):
    ModuleNotFoundError: import of nspak halted; None in sys.modules

    >>> nspak.foo.dofoo()  # installs requirements and unlocks dependants
    installing regex==2024.4.16 (Alternative regular expression module, to replace re.)
    hello regex

    >>> import nspak  # OK

    Importing requirements directly is also possible, but must use a `requirements.txt` resource from some package.

    >>> with LazyImportGroup('pak:itk-demo-requirements.txt'):
    ...     import itk

    >>> itk.Fpfh.PointFeature.MF3MF3.New()  # doctest: +ELLIPSIS
    installing itk==5.3.0 (ITK is an open-source toolkit for multidimensional image analysis)
    installing itk-fpfh==0.1.1 (An ITK-based implementation of FPFH ...)
    <itk.itkPointFeaturePython.itkPointFeatureMF3MF3; proxy of ...>

    The proxy module and the real module may not be the same, but one can extract the real module from the proxy.

    >>> with LazyImportGroup('pak:requirements.txt'):
    ...     import fuzzywuzzy.fuzz as lazy_fz
    >>> _ = lazy_fz.ratio  # resolve lazy import
    >>> import fuzzywuzzy.fuzz as real_fz

    >>> lazy_fz is real_fz
    False
    >>> lazy_fz.ratio is real_fz.ratio
    True
    >>> real_module(lazy_fz) is real_fz
    True

    See the requirements.txt docs for the full list of features:

    - https://pip.pypa.io/en/stable/reference/requirement-specifiers/
    - https://pip.pypa.io/en/stable/reference/requirements-file-format/
    - https://pip.pypa.io/en/stable/topics/vcs-support/
    - https://pip.pypa.io/en/stable/topics/secure-installs/

    notably:

        - specific versions (eg. fuzzywuzzy==0.18.0)
        - version constraints (eg. fuzzywuzzy>=0.17)
        - platform constraints (eg. importlib_metadata ; python_version < '3.10')
        - URL-based specifiers (eg. pip @ https://github.com/pypa/pip/archive/22.0.2.zip)
        - git specifiers (eg. MyProject @ git+https://git.example.com/MyProject.git@da39a3ee)
        - hash checking

    Best practice would be to use a _constrained_, but not pinned, version of a pypi package.
    else use a github zip archive with hash checking.
    else use a github repository with tag or sha.
    """

    def __init__(self, requires, name=None):
        self.requires = requires
        self.name = name

        self.finder = VeryLazyFinder(self)
        self.modules = {}

        self.need_install = True  # so that only the first invocation of resolve() runs pip.

    def __enter__(self):
        sys.meta_path.insert(0, self.finder)

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.meta_path.remove(self.finder)
        self.lock()

    def register(self, module: "VeryLazyModule"):
        self.modules[module.__spec__.name] = module

    def lock(self):
        for name, module in self.modules.items():
            if sys.modules[name] is module:
                sys.modules[name] = None  # noqa: Explicitly prevent imports.

    def unlock(self):
        for name in self.modules:
            if name in sys.modules and sys.modules[name] is None:
                # remove None entries for self.modules to allow imports again.
                del sys.modules[name]

    def resolve(self):
        if not self.need_install:
            return

        # `importlib.resources.files` would actually import the package; but then we can't ensure dependencies.
        # So create a dummy module from the package spec - but do not execute it - `importlib.resources.files`
        # can use it to locate resources without importing the package.
        #
        # Note this might fail if some package `__init__` is meant to generate the resource; but it will work
        # for any resources installed via cmake macro.

        pak, _, req = self.requires.rpartition(":")
        spec = importlib.util.find_spec(pak)
        dummy = importlib.util.module_from_spec(spec)
        resource = importlib.resources.files(dummy).joinpath(req)

        with importlib.resources.as_file(resource) as requires:
            with tempfile.NamedTemporaryFile("r") as freport:
                pip(
                    [
                        "install",
                        *EXTRA_PIP_ARGS,
                        "--dry-run",
                        "--no-deps",
                        "--report",
                        freport.name,
                        "-r",
                        str(requires),
                    ]
                )
                report = json.load(freport)

            # todo use slicer.util.confirmOkCancelDisplay to show install summary and abort install if user opts out
            for entry in report["install"]:
                print("installing {name}=={version} ({summary})".format_map(entry["metadata"]))

            if report["install"]:
                pip(["install", *EXTRA_PIP_ARGS, "-r", str(requires)])

        self.need_install = False


class VeryLazyModule(types.ModuleType):
    """
    Defer module execution to first usage.

    A module with this type has not been executed - on first attribute access:
    - resolve dependencies
    - find the _real_ spec
    - execute the module

    This module object `self` is a proxy object for the true module; proxy objects are identified by
    their __real_module__ attribute. The contents of the modules are otherwise the same objects.
    """

    def __getattr__(self, attr):
        self.__class__ = types.ModuleType

        group: LazyImportGroup = self.__spec__.loader_state
        group.unlock()
        group.resolve()

        self.__real_module__ = importlib.import_module(self.__spec__.name)
        self.__dict__.update(self.__real_module__.__dict__)

        return getattr(self, attr)


def real_module(module: types.ModuleType) -> types.ModuleType:
    """Get the real module object from a lazy proxy module."""
    return getattr(module, "__real_module__", module)


class VeryLazyLoader(importlib.abc.Loader):
    """
    Set module type to VeryLazyModule so it will be imported on first access, and mark the module
    object as part of the import group for lock/unlock.
    """

    def exec_module(self, module):
        module.__class__ = VeryLazyModule
        module.__spec__.loader_state.register(module)


class VeryLazyFinder(importlib.abc.MetaPathFinder):
    """
    Return a dummy spec for _all_ modules using VeryLazyLoader (and VeryLazyModule); find_spec
    never fails. The real import step occurs on first attribute access (see VeryLazyModule).
    """

    def __init__(self, group):
        self.loader = VeryLazyLoader()
        self.group = group

    def find_spec(self, fullname, path, target=None):
        return importlib.machinery.ModuleSpec(
            name=fullname,
            loader=VeryLazyLoader(),
            loader_state=self.group,
            is_package=True,
        )
