"""Regression tests: exact tapline contracts, hostile data, and offline lifecycle."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import warnings
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader('omarchy_we', str(ROOT / 'bin/omarchy-we'))
spec = importlib.util.spec_from_loader(loader.name, loader)
we = importlib.util.module_from_spec(spec)
loader.exec_module(we)


class Integration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.patches = [patch.object(we, key, self.base / name) for key, name in [('HOME','home'), ('DATA','data'), ('STATE','state'), ('CACHE','cache'), ('CURRENT','state/current')]]
        for p in self.patches:
            p.start()
        self.bin = self.base / 'bin'
        self.bin.mkdir()
        self.log = self.base / 'calls.jsonl'
        fake = self.bin / 'tapline'
        fake.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args=sys.argv[1:]
with open(os.environ['CALLS'],'a') as f: f.write(json.dumps(args)+'\\n')
if args[:2] == ['workshop','search']:
 print(json.dumps({'event':'result','app':431960,'item':'123456789','title':'<img src="https://tracker.invalid">','tags':['Scene'],'size':12}))
 print(json.dumps({'event':'searched','total':61,'next_cursor':None}))
elif args[:2] == ['workshop','info']:
 print(json.dumps({'event':'item','app':int(os.environ.get('APP','431960')),'item':args[2]}))
elif args[:2] == ['workshop','download']:
 p=Path(args[args.index('--dir')+1]);p.mkdir(parents=True,exist_ok=True)
 (p/'project.json').write_text(json.dumps({'type':'scene','title':'downloaded'}))
 print(json.dumps({'event':'workshop_completed'}))
elif args[:2] == ['app','download']:
 p=Path(args[args.index('--dir')+1])/'assets'
 for name in ('models/util/solidlayer.json','materials/util/solidlayer.json','shaders/genericimage.vert','shaders/genericimage.frag'):
  file=p/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_text('content')
 print(json.dumps({'event':'completed','app':431960}))
''')
        fake.chmod(0o755)
        self.env = patch.dict(os.environ, {'PATH': str(self.bin) + ':' + os.environ['PATH'], 'CALLS': str(self.log), 'XDG_CONFIG_HOME': str(we.HOME / '.config')}, clear=False)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_browse_passes_prefilled_search_as_json_argument(self):
        query = 'nature "quoted" $(not-a-command)'
        with patch.object(we, 'run') as run:
            we.main(['browse', query])
        argv = run.call_args.args[0]
        self.assertEqual(argv[:4], ['omarchy-shell','shell','summon',we.PLUGIN])
        self.assertEqual(json.loads(argv[4]), {'view':'workshop', 'query':query})
        with patch.object(we, 'run') as run:
            we.main(['browse'])
        self.assertEqual(json.loads(run.call_args.args[0][4])['query'], '')

    def test_search_literal_arguments_and_numbered_pagination(self):
        query = '$(touch /tmp/pwned) <img> "quote"'
        result = we.search(query, 2)
        self.assertEqual(result['items'][0]['title'], '<img src="https://tracker.invalid">')
        self.assertTrue(result['more'])
        self.assertIn(query, self.calls()[0])
        self.assertIn('Scene,Video', self.calls()[0])
        self.assertEqual(self.calls()[0][self.calls()[0].index('--page')+1], '2')

    def test_download_verifies_app_then_atomically_installs_flat(self):
        we.download('123456789')
        self.assertEqual(self.calls()[0], ['workshop','info','123456789','--json'])
        download = self.calls()[1]
        self.assertEqual(download[:4], ['workshop','download','431960','123456789'])
        self.assertIn('--flat', download)
        self.assertTrue((we.DATA / 'workshop/123456789/project.json').is_file())
        self.assertFalse((we.DATA / 'workshop/.123456789.partial').exists())
        self.assertEqual(we.library()[0]['title'], 'downloaded')

    def test_wrong_app_never_downloaded(self):
        with patch.dict(os.environ, {'APP': '440'}):
            with self.assertRaisesRegex(RuntimeError, 'does not belong'):
                we.download('123456789')
        self.assertEqual(len(self.calls()), 1)

    def test_assets_only_select_assets_folder(self):
        we.fetch_assets()
        call = self.calls()[0]
        self.assertEqual(call[:3], ['app','download','431960'])
        self.assertEqual(call[call.index('--path')+1], 'assets')
        self.assertIsNotNone(we.assets())

    def test_empty_managed_assets_do_not_shadow_valid_steam_assets(self):
        managed = we.DATA / 'engine/assets'
        (managed / 'shaders').mkdir(parents=True)
        (managed / 'materials').mkdir()
        steam = self.base / 'Steam'
        shared = steam / 'steamapps/common/wallpaper_engine/assets'
        for name in we.ASSET_REQUIRED_FILES:
            we.write(shared / name, 'content')
        with patch.object(we, 'steam_roots', return_value=[steam]):
            self.assertEqual(we.assets(), shared)
        (shared / we.ASSET_REQUIRED_FILES[0]).write_text('')
        self.assertFalse(we.assets_complete(shared))

    def test_incomplete_staging_cannot_report_success_or_replace_existing_assets(self):
        shared = we.DATA / 'engine/assets'
        for name in we.ASSET_REQUIRED_FILES:
            we.write(shared / name, 'old valid content')
        def fake_download(*args, **kwargs):
            (we.DATA / '.engine.partial/assets/shaders').mkdir(parents=True)
            return json.dumps({'event':'completed','app':431960})
        with patch.object(we, 'tap', side_effect=fake_download):
            with self.assertRaisesRegex(RuntimeError, 'incomplete'):
                we.fetch_assets()
        self.assertEqual((shared / we.ASSET_REQUIRED_FILES[0]).read_text(), 'old valid content')
        self.assertFalse((we.DATA / '.engine.previous').exists())

    def test_asset_download_replaces_only_after_validated_completion(self):
        shared = we.DATA / 'engine/assets'
        we.write(shared / 'old-unused-file', 'old')
        we.fetch_assets()
        self.assertTrue(we.assets_complete(shared))
        self.assertFalse((shared / 'old-unused-file').exists())
        self.assertFalse((we.DATA / '.engine.partial').exists())
        self.assertFalse((we.DATA / '.engine.previous').exists())
        self.assertEqual(self.calls()[0][self.calls()[0].index('--dir')+1], str(we.DATA / '.engine.partial'))

    def test_empty_library_and_doctor_need_no_steam_install(self):
        self.assertEqual(we.library(), [])
        self.assertEqual(we.doctor()['count'], 0)
        self.assertEqual(we.current()['running'], False)

    def test_untrusted_preview_cannot_escape_project(self):
        folder = we.DATA / 'workshop/123456789'
        folder.mkdir(parents=True)
        (we.DATA / 'outside.png').write_bytes(b'x')
        (folder / 'project.json').write_text(json.dumps({'type':'scene','title':'a\nb\tc', 'preview':'../../outside.png'}))
        result = we.library()[0]
        self.assertIsNone(result['preview'])
        self.assertEqual(result['title'], 'abc')

    def test_invalid_ids_rejected_before_network(self):
        for wid in ('../escape', '-1', '1;true', '0', str(2**64)):
            with self.assertRaises(RuntimeError):
                we.download(wid)
        self.assertFalse(self.log.exists())

    def test_preview_hosts_and_redirects_are_restricted(self):
        self.assertTrue(we.valid_preview_url('https://images.steamusercontent.com/ugc/123'))
        for url in ('http://images.steamusercontent.com/a', 'https://images.steamusercontent.com.evil/a', 'https://127.0.0.1/a', 'file:///etc/passwd', 'https://images.steamusercontent.com:bad/a', 'https://user@images.steamusercontent.com/a'):
            self.assertFalse(we.valid_preview_url(url), url)
        with self.assertRaises(RuntimeError):
            we.PreviewRedirect().redirect_request(None, None, 302, '', {}, 'http://127.0.0.1/private')

    def test_timeout_kills_child(self):
        with self.assertRaisesRegex(RuntimeError, 'timed out'):
            we.run(['python3','-c','import time; time.sleep(30)'], timeout=.1)

    def test_stale_renderer_pid_does_not_kill_another_process(self):
        we.write(we.STATE / 'renderer.json', json.dumps({'pid':os.getpid(),'start':'incorrect'}))
        self.assertIsNone(we.renderer_pid())
        we.kill_renderer()

    def test_stop_clears_selection_so_launch_wont_restart(self):
        we.write(we.CURRENT, '123456789')
        we.stop()
        self.assertFalse(we.CURRENT.exists())
        with patch.object(we, 'apply') as apply:
            we.main(['launch'])
        apply.assert_not_called()

    def test_renderer_receives_assets_monitors_and_restores_background(self):
        folder = we.DATA / 'workshop/123456789'
        folder.mkdir(parents=True)
        (folder / 'project.json').write_text(json.dumps({'type':'scene','title':'example'}))
        shared = we.DATA / 'engine/assets'
        for name in we.ASSET_REQUIRED_FILES:
            we.write(shared / name, 'content')
        renderer = self.bin / 'linux-wallpaperengine'
        renderer.write_text('#!/usr/bin/env python3\nimport time\ntime.sleep(30)\n')
        renderer.chmod(0o755)
        monitor = self.bin / 'hyprctl'
        monitor.write_text('#!/usr/bin/env python3\nprint(\'[{"name":"DP-1"},{"name":"HDMI-A-1"}]\')\n')
        monitor.chmod(0o755)
        previous = we.HOME / 'old.png'
        previous.parent.mkdir(parents=True)
        previous.write_bytes(b'previous')
        link = we.HOME / '.local/state/omarchy/current/background'
        link.parent.mkdir(parents=True)
        link.symlink_to(previous)
        pid = None
        try:
            with patch.object(we, 'background') as bg, warnings.catch_warnings():
                warnings.simplefilter('ignore', ResourceWarning)
                we.apply('123456789')
                pid = we.renderer_pid()
                self.assertIsNotNone(pid)
                args = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
                self.assertIn(str(shared).encode(), args)
                self.assertIn(b'DP-1', args)
                self.assertIn(b'HDMI-A-1', args)
                self.assertEqual(we.current_id(), '123456789')
                we.stop()
                self.assertEqual(bg.call_args.args, (previous,))
                self.assertFalse(we.CURRENT.exists())
        finally:
            if pid:
                try:
                    os.waitpid(pid, 0)
                except ChildProcessError:
                    pass

    def test_configured_disk_requires_mount_without_creating_fallback(self):
        config = we.HOME / '.config/omarchy-we/settings.json'
        mount = self.base / 'Games'
        we.write(config, json.dumps({'library':str(mount / 'library'), 'required_mount':str(mount)}))
        with patch.object(we.os.path, 'ismount', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'not mounted'):
                we.download('123456789')
        self.assertFalse(mount.exists())

    def test_configured_library_must_remain_inside_mount(self):
        config = we.HOME / '.config/omarchy-we/settings.json'
        we.write(config, json.dumps({'library':str(self.base/'outside'), 'required_mount':str(self.base/'Games')}))
        with patch.object(we.os.path, 'ismount', return_value=True):
            with self.assertRaisesRegex(RuntimeError, 'inside required_mount'):
                we.managed_root()

    def test_all_qml_text_sinks_are_plain_text(self):
        import re
        for filename in ('Workshop.qml','DialPicker.qml'):
            source = (ROOT / filename).read_text()
            for match in re.finditer(r'\bText\s*\{', source):
                tail = source[match.end():]
                depth, end = 1, 0
                for end, char in enumerate(tail):
                    depth += (char == '{') - (char == '}')
                    if depth == 0:
                        break
                self.assertIn('textFormat: Text.PlainText', tail[:end], filename)
        self.assertNotIn('"-c"', (ROOT / 'Service.qml').read_text())
        self.assertNotIn('"bash"', (ROOT / 'Workshop.qml').read_text())

    def test_translation_keys_match(self):
        en=json.loads((ROOT/'i18n/en.json').read_text())
        pt=json.loads((ROOT/'i18n/pt-BR.json').read_text())
        self.assertEqual(set(en), set(pt))


if __name__ == '__main__':
    unittest.main()
