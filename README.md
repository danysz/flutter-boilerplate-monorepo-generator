```markdown
# Daniel Szasz Flutter Boilerplate Automation Toolkit 🚀

A zero-touch Python orchestrator that generates a production-ready, highly automated Flutter mono-repo. It handles everything from Google Cloud provisioning and Firebase configuration to Keystore generation, Git initialization, and CI/CD script injection.

## ⚡ Quick Start

1. Download the `create_app.py` orchestrator script.
2. Run it in your terminal:
   ```bash
   python3 create_app.py
   ```
3. Answer the interactive prompts to define your app name, Firebase environments, and API URLs.
4. The script will automatically build your workspace, provision your cloud resources, extract your App IDs, and push the initial commit to GitHub.

## 🛠 Prerequisites

Before running the generator, ensure you have the following CLI tools installed:
* **Flutter** (`flutter`)
* **Firebase CLI** (`firebase`)
* **Google Cloud CLI** (`gcloud`)
* **FlutterFire CLI** (`flutterfire`)
* **Java Development Kit** (`keytool` - for Android Keystores)
* **Git** (`git`)

---

## 📁 Mono-Repo Architecture

This tool generates a scalable mono-repo structure, keeping your Flutter code separate from your automation scripts and security keys.

```text
your_app_name/           <-- Root Git Repository
├── .env                 <-- Auto-generated API URLs & Firebase App IDs (Ignored in Git)
├── .gitignore           <-- Pre-configured to protect secrets
├── mobile/              <-- The Flutter Application (iOS, Android, Web)
├── _keys/               <-- Secure Keystores (Ignored in Git)
└── scripts/             <-- CI/CD, Security, and Localization Automation
```

---

## 🤖 The Automation Scripts

During generation, the toolkit injects 9 distinct automation scripts into your `./scripts` directory. These are designed to provide a "zero manual work" pipeline.

### 🚀 CI/CD & Deployment
These scripts handle semantic versioning and push your code to Firebase App Distribution or web hosts.

* **`deploy_mobile.sh [d|p|dp]`**
  * **What it does:** The master deployment orchestrator. It reads your `.env` file securely, builds the requested flavor (`d` for dev, `p` for prod, `dp` for both), and uploads the APK and IPA directly to Firebase App Distribution.
  * **Usage:** `cd your_app_name && ./scripts/deploy_mobile.sh d`
* **`deploy_web_test.sh`**
  * **What it does:** Isolates the `/mobile` directory using a git subtree and force-pushes your Flutter Web build to a remote testing server.
* **`bump_mobile_version.sh`**
  * **What it does:** Automates semantic versioning. It parses `pubspec.yaml`, increments the patch or minor version, updates the integer build number, and automatically commits the change to Git.

### 🔐 Security & Authentication
Manage your cryptographic keys and Google Sign-In requirements effortlessly.

* **`generate_keystore.sh`**
  * **What it does:** Safely creates your 2048-bit RSA production Android keystore. It includes an overwrite-protection safeguard to ensure you never accidentally delete a production key.
* **`setup_firebase_auth.sh`**
  * **What it does:** Extracts the SHA-1 and SHA-256 certificate fingerprints from both your local debug keystore and your production keystore, formatting them perfectly so you can paste them into the Firebase Console for Google Sign-In.

### 🌍 Localization (l10n) Automation
Flutter's native localization requires significant boilerplate. This pipeline automates the extraction and fixing of hardcoded UI strings.

* **`run_l10n_pipeline.sh`**
  * **What it does:** The master orchestrator for localization. Run this after coding a new screen to automatically move hardcoded English strings into your translation files and fix Dart errors.
* **`extract_strings.py`**
  * **What it does:** Uses RegEx to scan `.dart` files for hardcoded text (e.g., `Text('Hello')`), generates a camelCase key, injects it into `app_en.arb`, and replaces the Dart code with `AppLocalizations.of(context)!.key`.
* **`fix_analyze.py`**
  * **What it does:** Reads `flutter analyze` logs to find `invalid_constant` errors caused by string extraction, intelligently stripping the `const` keyword from parent widgets.
* **`fix_context.py`**
  * **What it does:** Solves edge cases by automatically injecting required `BuildContexts` into `DataGridSource` classes so the localization engine can access them.

---

## 📄 License

This project is licensed under the **GNU General Public License v3.0 (GPLv3)**. 

We encourage developers to fork, improve, and build upon this toolkit! However, under the GPLv3 license, any modifications or enhancements you distribute must also be made open-source under the same license to benefit the broader community. 
```
