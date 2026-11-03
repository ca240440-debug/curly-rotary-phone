# iOS, Android, and web installation

## What exists

- Shared mobile-friendly UI, local API, illustrated sample discovery, parental gates.
- Generated Capacitor 8.6.0 Android and iOS source projects in `android/` and `ios/`.
- Pinned npm dependencies and lockfile; native asset preparation and sync commands.
- Web manifest and service worker with no data caching. Optional web Share Target routes through adult review.

The Android/iOS source scaffolds were generated and synchronized in this Linux environment. They have **not** been compiled, installed, signed, or published. Android SDK/Android Studio and Apple Xcode are not configured here. Generated default native icons/splash and the `com.example.wishnest` application ID are development placeholders.

## Reproduce platform scaffolds

```sh
npm ci
npm run mobile:scaffold
npm run mobile:sync
```

Scaffold mode intentionally does not configure an API and displays an unconnected preview screen. It is not a working offline family app or release build.

## Prepare a connected device build

First provision an appropriate HTTPS backend with production security, accounts/family isolation, adult consent, and privacy controls. Do not expose the prototype's single-family loopback server as a public service.

On a deployment that intentionally permits the app, explicitly configure the backend CORS origin allowlist:

```text
WISHNEST_APP_ORIGINS=capacitor://localhost,https://localhost
```

No wildcard or credential values are needed. The backend still validates role/session permissions. API request origins must also be validated at any reverse proxy. TLS termination and origin checks must be hardened for production; current local origin checks assume HTTP for same-origin web requests.

On the build machine, prepare assets with your real HTTPS backend origin (no path/query/credentials), then sync:

```sh
WISHNEST_API_BASE=https://your-backend.example npm run mobile:prepare
npm run mobile:sync
npm run mobile:android
# On macOS with Xcode:
npm run mobile:ios
```

Replace the example domain and app identifier with resources you own. The preparation script rejects non-HTTPS endpoints. It embeds only the API origin, never secrets. Native HTML CSP restricts connections to that explicit origin. Sessions stay in memory; reopening the app requires sign-in again. Device lifecycle, safe areas, accessibility, background behavior, and external-link handling need actual iOS/Android testing.

Android requires the SDK/JDK versions selected by the generated Gradle project and signing credentials for release. iOS requires a supported macOS/Xcode toolchain, Apple developer provisioning, and signing. Supply signing material securely outside source control. Complete store policies, age ratings, privacy disclosures, parental consent, accessibility, native icons, device testing, and account review before distributing.

## Optional web app installation and sharing

Serve the web app from a suitable HTTPS origin for real mobile use (localhost is only a development exception). Compatible browsers can install it from the manifest. Web Share Target is primarily available on supported installed Android web apps; platform support varies. A received URL is never imported automatically. `/share` opens the app, holds the URL temporarily in memory, and asks an adult to sign in and review it. Do not share credentials or sensitive personal text. iOS native share extensions and Android native ACTION_SEND receivers are future work; they should reuse the same gated import service.

The service worker does not cache API responses, wishes, catalog permissions, or family data, so this version requires an online backend and does not offer offline authenticated access.
