# setup-android-cli

[![CI](https://github.com/premex-ab/setup-android-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/premex-ab/setup-android-cli/actions/workflows/ci.yml)

A GitHub Action that installs Google's agent-first [`android` CLI](https://developer.android.com/tools/agents/android-cli), sets up the Android SDK, and caches between runs. An alternative to [`setup-android`](https://github.com/android-actions/setup-android) with explicit SDK packages and caching.

## Why switch?

| | `setup-android` | `setup-android-cli` |
|---|---|---|
| Download size | ~300 MB (cmdline-tools zip) | ~5 MB (single binary) |
| Install | Unzip + accept licenses + sdkmanager | `curl` one binary |
| Package syntax | `"platforms;android-34"` (semicolons) | `platforms/android-34` (slashes) |
| License prompt | `yes \| sdkmanager --licenses` | Auto-accepted, non-interactive |
| Action type | JavaScript (Node 20, bundled) | Composite (pure YAML + shell) |
| Version tracking | Pin a cmdline-tools build number | Always installs the current CLI release |

## Usage

### Basic

```yaml
steps:
  - uses: actions/checkout@v4
  - uses: actions/setup-java@v4
    with:
      distribution: temurin
      java-version: '21'
  - uses: premex-ab/setup-android-cli@v1
    with:
      packages: platform-tools
  - run: ./gradlew --no-daemon build
```

### Multiple packages

```yaml
  - uses: premex-ab/setup-android-cli@v1
    with:
      packages: |
        platforms/android-34
        build-tools/34.0.0
        platform-tools
```

### CLI only (no SDK packages)

```yaml
  - uses: premex-ab/setup-android-cli@v1
  - run: android --version
```

### Custom SDK path

```yaml
  - uses: premex-ab/setup-android-cli@v1
    with:
      sdk-path: /opt/android-sdk
      packages: platforms/android-34 build-tools/34.0.0 platform-tools
```

### Disable caching

```yaml
  - uses: premex-ab/setup-android-cli@v1
    with:
      cache: 'false'
      packages: platform-tools
```

## Inputs

| Input | Default | Description |
|---|---|---|
| `packages` | `''` | SDK packages to install, space- or newline-separated (slash syntax). Empty = CLI only. |
| `sdk-path` | platform default | Override SDK install location. Exported as both `ANDROID_HOME` and `ANDROID_SDK_ROOT`. |
| `cache` | `'true'` | Cache `~/.android/bin` and the SDK between runs. |
| `cache-key` | `''` | Extra input appended to cache key (for busting). |
| `no-metrics` | `'true'` | Pass `--no-metrics` to opt out of CLI telemetry. |
| `install-url-base` | Google redirector | Override download URL base (for mirrors / air-gap). |

## Outputs

| Output | Description |
|---|---|
| `sdk-path` | Absolute path to the installed Android SDK. |
| `cli-version` | Version string from `android --version`. |
| `cache-hit` | Whether the cache was restored (`true`/`false`, empty if caching disabled). |

## Environment

The action exports the following environment variables for subsequent steps:

| Variable | Description |
|---|---|
| `ANDROID_HOME` | Absolute path to the SDK. Set for back-compat with older tooling. |
| `ANDROID_SDK_ROOT` | Same value as `ANDROID_HOME`. Set because newer Android tooling (AGP 8.x, recent Gradle plugins, the cmdline-tools `sdkmanager`) reads this variable first and only falls back to `ANDROID_HOME` when it is unset. |

## What it does

1. Downloads the current `android` CLI launcher (`android.exe` on Windows) into the runner's tool cache on every run, including persistent self-hosted runners.
2. Unpacks embedded resources on first run into `~/.android/bin/` (~78 MB, cached).
3. Exports `ANDROID_HOME` and `ANDROID_SDK_ROOT`, and adds `platform-tools/`, `emulator/`, and `cmdline-tools/latest/bin/` to `PATH`.
4. Runs `android sdk install <packages>` if packages are specified.
5. Registers Gradle, Kotlin, and Android Lint [problem matchers](https://github.com/actions/toolkit/blob/main/docs/problem-matchers.md) so build errors show inline in the GitHub UI.
6. Writes a job summary table with CLI version, SDK path, and cache status.

## Supported runners

| Runner | Status |
|---|---|
| `ubuntu-latest` / `ubuntu-22.04` | Supported |
| `macos-latest` / `macos-14` (Apple Silicon) | Supported |
| `macos-13` (Intel, Rosetta) | Best-effort (warning emitted) |
| Windows x64 | Supported with Git Bash on PATH; SDK/build tools only, not `android emulator` |
| Self-hosted Linux x86_64 / macOS arm64 | Supported |

## Caching

By default the action caches `~/.android/bin` (CLI resources, ~78 MB) and the full SDK directory between runs. The cache key includes OS, architecture, and the hash of `**/libs.versions.toml`, `**/build.gradle*`, and `**/settings.gradle*` plus a hash of the requested packages, resolved SDK path, and download URL. Changing workflow inputs therefore invalidates the SDK cache too. `ANDROID_USER_HOME`, when set, determines where CLI resources are cached.

Gradle caching is **not** handled by this action. Use [`gradle/actions/setup-gradle@v4`](https://github.com/gradle/actions) for that.

## Windows self-hosted runners

The action uses Git Bash, including `curl` and `cygpath`, supplied by Git for Windows.
Install Git for Windows and ensure the runner service can find `bash` on PATH.
Java must be available for Gradle builds. SDK setup supports Windows x64;
Google's `android emulator` command currently does not support Windows.

```yaml
jobs:
  build:
    runs-on: [self-hosted, windows, x64]
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '21'
      - uses: premex-ab/setup-android-cli@v1
        with:
          packages: platforms/android-36 build-tools/36.0.0 platform-tools
      - run: ./gradlew.bat assembleDebug
```

The default SDK path is `%LOCALAPPDATA%/Android/Sdk`; custom paths containing
spaces are supported. Paths exported through `ANDROID_HOME`, `ANDROID_SDK_ROOT`,
and the action outputs work in subsequent PowerShell steps as well as Git Bash.

## Migrating from `setup-android`

```diff
 - name: Setup Android SDK
-  uses: android-actions/setup-android@v3
-  with:
-    packages: 'tools platform-tools'
+  uses: premex-ab/setup-android-cli@v1
+  with:
+    packages: platform-tools
```

Key differences:
- Specify every required platform and build-tools package explicitly. The default
  installs only the CLI and does not adopt the runner's preinstalled SDK path.
- No `cmdline-tools-version` input (always current release). A custom
  `install-url-base` can select a versioned mirror; the launcher is refreshed each run.
- Direct `sdkmanager`/`avdmanager` calls are not provided by the CLI launcher.
  Migrate them separately or explicitly install the required command-line tools.
- No `accept-android-sdk-licenses` input (auto-accepted).
- Package names use slashes instead of semicolons: `platforms/android-34` not `"platforms;android-34"`.
- `tools` package doesn't exist in the new CLI; drop it.

## Problem matchers

This action registers problem matchers for:
- Android Lint warnings and errors
- Gradle build errors
- Kotlin compiler warnings and errors

These surface build issues as inline annotations in the GitHub UI.

## License

[MIT](LICENSE)
