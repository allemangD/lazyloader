A context manager which temporarily defers `import` statements till first usage, installing dependencies.

---

This demo uses doctests; the summary below is the doctest for `LazyImportGroup`.

---

```py
with LazyImportGroup('pak:requirements.txt'):
    import pak
```

`import pak` here creates a dummy `VeryLazyModule` which defers execution till first attribute access.

```py
pak.dopak()  # lazily triggers `pip install -r requirements.txt` and `import pak`
#  ^ attribute access triggers install and import
```

The requirements file is specified in the form `package:resource` where `package` and `resource` are passed to
`importlib.resources` to locate the resource. For example `pak:requirements.txt` finds the `requirements.txt`
resource in the `pak` package.

All imports within a LazyImportGroup share the same requirements, and installation is only triggered once.

```py
with LazyImportGroup('pak:requirements.txt'):
    import pak
    import pak.bar

pak.dopak()  # triggers pip install -r requirements.txt
pak.bar.dobar()  # module is already loaded; no installation
```

Raw `import` of a lazily-imported module outside the context manager is illegal when the requirements are not
guaranteed to be satisfied. This is explicitly disabled, so such raw imports will produce `ImportError`, even
if the dependencies happen to be met in the particular environment. This hels developers catch the error that
a package might be installed in their environment, but not during first usage on a user's environment.

Once some module in the import group is resolved, all the dependencies are installed together and the other
modules in the group are unlocked. This means lazily-imported modules can safely contain raw relative imports
and top-level dependency imports, since the group dependencies are guaranteed to be met.

```py
with LazyImportGroup('nspak:requirements.txt'):
    import nspak.foo

try:
    import nspak  # ImportError; explicitly disabled
except ImportError:
    pass

nspak.foo.dofoo()  # installs requirements and unlocks dependants

import nspak  # OK
```

Importing requirements directly is also possible, but must use a `requirements.txt` resource from some package.

```py
with LazyImportGroup('pak:itk-demo-requirements.txt'):
    import itk

_ = itk.Fpfh.PointFeature.MF3MF3.New()
```

See the requriements docs for the full list of features:

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

---

This demo uses `pip install --dry-run --no-deps --report` to quickly resolve dependencies to present a summary of
changes. Slicer integration should use this to create a confirmation prompt for the user.

Note that `uv` does not support the `--report` argument, so generating a summary is more difficult.

See `LazyImportGroup.resolve`.
