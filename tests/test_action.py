"""Exercise the actual composite-action scripts with an isolated fake download."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
ACTION = yaml.safe_load((ROOT / 'action.yml').read_text())
STEPS = {step['name']: step['run'] for step in ACTION['runs']['steps'] if 'run' in step}


class ActionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='android action ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.env = dict(os.environ, HOME=str(self.root), RUNNER_OS='Linux',
                        RUNNER_TOOL_CACHE=str(self.root / 'tool cache'),
                        INPUT_SDK_PATH=str(self.root / 'sdk with spaces'),
                        PACKAGES='platform-tools\nplatforms/android-36',
                        INSTALL_URL_BASE='https://example.invalid/cli/latest',
                        NO_METRICS='true', CACHE_HIT='',
                        CALLS=str(self.root / 'calls.jsonl'),
                        PATH=str(self.bin) + os.pathsep + os.environ['PATH'])
        self.env.pop('ANDROID_USER_HOME', None)
        for key in ['GITHUB_OUTPUT', 'GITHUB_ENV', 'GITHUB_PATH', 'GITHUB_STEP_SUMMARY']:
            path = self.root / key
            path.touch()
            self.env[key] = str(path)
        self.script('uname', 'import sys\nprint("Linux" if sys.argv[1] == "-s" else "x86_64")\n')
        self.launcher = self.root / 'downloaded launcher'
        self.launcher.write_text(f'#!{sys.executable}\n' + '''import json, os, sys
with open(os.environ['CALLS'], 'a') as stream:
    stream.write(json.dumps(sys.argv[1:]) + '\\n')
if '--version' in sys.argv:
    print('Android CLI test-version')
''')
        self.env['FAKE_LAUNCHER'] = str(self.launcher)
        self.script('curl', '''import os, shutil, sys
shutil.copyfile(os.environ['FAKE_LAUNCHER'], sys.argv[sys.argv.index('-o') + 1])
''')

    def script(self, name, body):
        path = self.bin / name
        path.write_text(f'#!{sys.executable}\n' + body)
        path.chmod(0o755)

    def run_step(self, name):
        return subprocess.run(['bash', '-c', STEPS[name]], env=self.env,
                              text=True, capture_output=True, check=True)

    def outputs(self, key='GITHUB_OUTPUT'):
        return dict(line.split('=', 1) for line in Path(self.env[key]).read_text().splitlines())

    def resolve(self):
        self.run_step('Resolve platform and paths')
        outputs = self.outputs()
        self.env.update(SLUG=outputs['slug'], TOOL_DIR=outputs['tool-dir'],
                        BINARY=outputs['binary'], SDK_PATH=outputs['sdk-path'])
        return outputs

    def install(self):
        self.run_step('Install CLI launcher')
        self.env['PATH'] = self.env['TOOL_DIR'] + os.pathsep + self.env['PATH']

    def test_cache_identity_tracks_workflow_inputs(self):
        baseline = self.resolve()['config-hash']
        self.assertEqual(baseline, self.resolve()['config-hash'])
        for key, value in [('PACKAGES', 'platform-tools platforms/android-35'),
                           ('INPUT_SDK_PATH', str(self.root / 'other sdk')),
                           ('INSTALL_URL_BASE', 'https://example.invalid/pinned')]:
            with self.subTest(key=key):
                previous = self.env[key]
                self.env[key] = value
                self.assertNotEqual(baseline, self.resolve()['config-hash'])
                self.env[key] = previous

    def test_persistent_launcher_refresh_paths_and_metrics(self):
        self.resolve()
        stale = Path(self.env['TOOL_DIR']) / 'android'
        stale.write_text('#!/bin/sh\nexit 19\n')
        stale.chmod(0o755)
        self.install()
        self.run_step('Configure ANDROID_HOME and ANDROID_SDK_ROOT')
        self.run_step('Install SDK packages')
        self.run_step('Summary')
        calls = [json.loads(line) for line in Path(self.env['CALLS']).read_text().splitlines()]
        self.assertEqual(calls, [
            ['--no-metrics', '--version'],
            ['--no-metrics', '--sdk=' + self.env['SDK_PATH'], 'sdk', 'install',
             'platform-tools', 'platforms/android-36'],
            ['--no-metrics', '--version'],
        ])
        self.assertEqual(self.outputs('GITHUB_ENV')['ANDROID_HOME'], self.env['SDK_PATH'])
        self.assertEqual(self.outputs()['cli-version'], 'Android CLI test-version')

    def test_metrics_can_be_enabled_without_empty_arguments(self):
        self.env['NO_METRICS'] = 'false'
        self.resolve()
        self.install()
        self.run_step('Install SDK packages')
        self.run_step('Summary')
        calls = [json.loads(line) for line in Path(self.env['CALLS']).read_text().splitlines()]
        self.assertEqual(calls[0], ['--version'])
        self.assertEqual(calls[-1], ['--version'])
        self.assertTrue(all('' not in call and '--no-metrics' not in call for call in calls))

    def test_custom_android_user_home_is_cached(self):
        self.env['ANDROID_USER_HOME'] = str(self.root / 'custom android home')
        self.assertEqual(self.resolve()['resources'], self.env['ANDROID_USER_HOME'] + '/bin')


if __name__ == '__main__':
    unittest.main()
