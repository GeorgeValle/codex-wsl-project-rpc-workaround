"""Packaging-specific filesystem safety tests."""

from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from _safety_support import (
    PACKAGING_VENV,
    SETUPTOOLS_WHEEL,
    prepare_disposable_directory,
    repository_cache_dir,
    repository_disposable_dir,
    require_absent_editable_egg_info,
    validate_setuptools_wheelhouse,
)


class SetuptoolsWheelhouseTests(unittest.TestCase):
    def sandbox(self):
        return tempfile.TemporaryDirectory(prefix="wheelhouse-boundary-", dir=repository_cache_dir())

    def fixture(self, temporary):
        root = Path(temporary)
        cache = root / ".cache"
        wheelhouse = cache / "codex-wsl-rpc-wheelhouse"
        wheelhouse.mkdir(parents=True)
        return root, cache, wheelhouse

    def test_valid_local_wheelhouse_is_accepted(self):
        with self.sandbox() as temporary:
            root, cache, wheelhouse = self.fixture(temporary)
            contents = b"controlled test wheel contents"
            wheel = wheelhouse / SETUPTOOLS_WHEEL
            wheel.write_bytes(contents)
            self.assertEqual(validate_setuptools_wheelhouse(wheelhouse, cache, root, hashlib.sha256(contents).hexdigest()), wheel.resolve())

    def test_symbolic_link_wheelhouse_is_rejected(self):
        with self.sandbox() as temporary:
            root = Path(temporary); cache = root / ".cache"; cache.mkdir()
            target = cache / "target"; target.mkdir(); wheelhouse = cache / "codex-wsl-rpc-wheelhouse"
            try: wheelhouse.symlink_to(target, target_is_directory=True)
            except OSError as error: self.skipTest(f"symbolic-link creation is unavailable: {error}")
            with self.assertRaisesRegex(AssertionError, "symbolic link"):
                validate_setuptools_wheelhouse(wheelhouse, cache, root)

    def test_missing_wheelhouse_is_rejected(self):
        with self.sandbox() as temporary:
            root = Path(temporary); cache = root / ".cache"; cache.mkdir(); wheelhouse = cache / "codex-wsl-rpc-wheelhouse"
            with self.assertRaisesRegex(AssertionError, "does not exist"):
                validate_setuptools_wheelhouse(wheelhouse, cache, root)

    def test_unexpected_entries_are_rejected(self):
        for name in ("setuptools-83.0.0-py3-none-any.whl", "unrelated.txt"):
            with self.subTest(name=name), self.sandbox() as temporary:
                root, cache, wheelhouse = self.fixture(temporary)
                (wheelhouse / name).write_bytes(b"unexpected")
                with self.assertRaises(AssertionError): validate_setuptools_wheelhouse(wheelhouse, cache, root)

    def test_additional_entries_are_rejected(self):
        with self.sandbox() as temporary:
            root, cache, wheelhouse = self.fixture(temporary)
            approved = wheelhouse / SETUPTOOLS_WHEEL; approved.write_bytes(b"expected")
            (wheelhouse / "setuptools-85.0.0-py3-none-any.whl").write_bytes(b"additional")
            with self.assertRaisesRegex(AssertionError, "exactly one"):
                validate_setuptools_wheelhouse(wheelhouse, cache, root)

    def test_symbolic_link_candidates_are_rejected(self):
        with self.sandbox() as temporary:
            root, cache, wheelhouse = self.fixture(temporary)
            target = cache / "target"; target.write_bytes(b"target")
            wheel = wheelhouse / SETUPTOOLS_WHEEL
            try: wheel.symlink_to(target)
            except OSError as error: self.skipTest(f"symbolic-link creation is unavailable: {error}")
            with self.assertRaisesRegex(AssertionError, "symbolic link"):
                validate_setuptools_wheelhouse(wheelhouse, cache, root)

    def test_directory_entry_is_rejected(self):
        with self.sandbox() as temporary:
            root, cache, wheelhouse = self.fixture(temporary); (wheelhouse / SETUPTOOLS_WHEEL).mkdir()
            with self.assertRaisesRegex(AssertionError, "regular file"):
                validate_setuptools_wheelhouse(wheelhouse, cache, root)

    def test_incorrect_sha256_is_rejected(self):
        with self.sandbox() as temporary:
            root, cache, wheelhouse = self.fixture(temporary); (wheelhouse / SETUPTOOLS_WHEEL).write_bytes(b"wrong")
            with self.assertRaisesRegex(AssertionError, "SHA-256"):
                validate_setuptools_wheelhouse(wheelhouse, cache, root)


class PackagingPathTests(unittest.TestCase):
    def sandbox(self):
        return tempfile.TemporaryDirectory(prefix="packaging-boundary-", dir=repository_cache_dir())

    def test_disposable_directory_boundaries(self):
        with self.sandbox() as temporary:
            root=Path(temporary); cache=root/'.cache'; cache.mkdir(); path=cache/'packaging-tmp'
            self.assertEqual(repository_disposable_dir(path, cache, root), path.resolve())
            bad=root/'other'/'packaging-tmp'; bad.parent.mkdir()
            with self.assertRaises(AssertionError): repository_disposable_dir(bad, cache, root)
            self.assertFalse(bad.exists())

    def test_disposable_symlink_and_file_are_rejected(self):
        with self.sandbox() as temporary:
            root=Path(temporary); cache=root/'.cache'; cache.mkdir(); target=cache/'target'; target.mkdir(); path=cache/'packaging-tmp'
            try: path.symlink_to(target, target_is_directory=True)
            except OSError as error: self.skipTest(f"symbolic-link creation is unavailable: {error}")
            with self.assertRaises(AssertionError): repository_disposable_dir(path, cache, root)
        with self.sandbox() as temporary:
            root=Path(temporary); cache=root/'.cache'; cache.mkdir(); path=cache/'packaging-tmp'; path.write_text('file')
            with self.assertRaises(AssertionError): repository_disposable_dir(path, cache, root)

    def test_fresh_venv_handling(self):
        with self.sandbox() as temporary:
            root=Path(temporary); cache=root/'.cache'; path=cache/PACKAGING_VENV.name; path.mkdir(parents=True); (path/'stale').write_text('x')
            self.assertEqual(prepare_disposable_directory(path, remove_existing=True, cache=cache, root=root), path)
            self.assertFalse(path.exists())

    def test_venv_symlink_file_and_out_of_cache_are_rejected(self):
        with self.sandbox() as temporary:
            root=Path(temporary); cache=root/'.cache'; cache.mkdir(); target=cache/'target'; target.mkdir(); path=cache/PACKAGING_VENV.name
            try: path.symlink_to(target, target_is_directory=True)
            except OSError as error: self.skipTest(f"symbolic-link creation is unavailable: {error}")
            with self.assertRaises(AssertionError): prepare_disposable_directory(path, remove_existing=True, cache=cache, root=root)
        with self.sandbox() as temporary:
            root=Path(temporary); cache=root/'.cache'; cache.mkdir(); path=cache/PACKAGING_VENV.name; path.write_text('file')
            with self.assertRaises(AssertionError): prepare_disposable_directory(path, remove_existing=True, cache=cache, root=root)
        with self.sandbox() as temporary:
            root=Path(temporary); cache=root/'.cache'; cache.mkdir(); path=root/'other'/PACKAGING_VENV.name; path.mkdir(parents=True)
            with self.assertRaises(AssertionError): prepare_disposable_directory(path, remove_existing=True, cache=cache, root=root)
            self.assertTrue(path.exists())


class EditableEggInfoTests(unittest.TestCase):
    def sandbox(self):
        return tempfile.TemporaryDirectory(prefix="egg-info-boundary-", dir=repository_cache_dir())

    def fixture(self, temporary):
        root = Path(temporary); src = root / "src"; src.mkdir()
        return src, src / "codex_wsl_rpc.egg-info"

    def test_absent_egg_info_is_accepted(self):
        with self.sandbox() as temporary:
            src, egg_info = self.fixture(temporary)
            self.assertEqual(require_absent_editable_egg_info(egg_info, src), egg_info)

    def test_symlinked_egg_info_is_rejected(self):
        with self.sandbox() as temporary:
            src, egg_info = self.fixture(temporary); target = src / "target"; target.mkdir()
            try: egg_info.symlink_to(target, target_is_directory=True)
            except OSError as error: self.skipTest(f"symbolic-link creation is unavailable: {error}")
            with self.assertRaisesRegex(AssertionError, "symbolic link"):
                require_absent_editable_egg_info(egg_info, src)

    def test_existing_directory_is_rejected(self):
        with self.sandbox() as temporary:
            src, egg_info = self.fixture(temporary); egg_info.mkdir()
            with self.assertRaisesRegex(AssertionError, "must be absent"):
                require_absent_editable_egg_info(egg_info, src)

    def test_existing_file_is_rejected(self):
        with self.sandbox() as temporary:
            src, egg_info = self.fixture(temporary); egg_info.write_text("stale")
            with self.assertRaisesRegex(AssertionError, "must be absent"):
                require_absent_editable_egg_info(egg_info, src)


if __name__ == "__main__":
    unittest.main()
