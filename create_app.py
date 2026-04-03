import os
import subprocess
import sys
import re
import shutil
import json
import time

# ==========================================
# UTILITY FUNCTIONS
# ==========================================

def check_dependencies():
    """Checks if all required CLI tools are installed before proceeding."""
    print("\n--- 🔍 Checking System Dependencies ---")
    missing_tools = False
    dependencies = {
        "flutter": "Visit https://docs.flutter.dev/get-started/install to install Flutter.",
        "firebase": "Run 'npm install -g firebase-tools' (requires Node.js).",
        "gcloud": "Visit https://cloud.google.com/sdk/docs/install to install the Google Cloud CLI.",
        "flutterfire": "Run 'dart pub global activate flutterfire_cli'.",
        "keytool": "Install the Java Development Kit (JDK).",
        "git": "Visit https://git-scm.com/downloads to install Git."
    }

    for cmd, install_instructions in dependencies.items():
        if shutil.which(cmd) is None:
            print(f"❌ Missing: {cmd}\n   👉 Fix: {install_instructions}")
            missing_tools = True
        else:
            print(f"✅ Found: {cmd}")

    if missing_tools:
        print("\n🚨 Missing dependencies detected. Please install them and try again.")
        sys.exit(1)
    print("🎉 All required tools are installed!\n")

def check_auth():
    """Verifies that the user is authenticated with Google Cloud and Firebase."""
    print("\n--- 🔐 Checking Cloud Authentication ---")
    
    print("Checking Google Cloud login...")
    if run_cmd("gcloud auth print-access-token", capture=True, quiet=True).returncode != 0:
        print("⚠️  You are not logged into Google Cloud. Launching login flow...")
        subprocess.run("gcloud auth login", shell=True)
    else:
        account = run_cmd("gcloud config get-value account", capture=True, quiet=True).stdout.strip()
        print(f"✅ Authenticated with GCP: {account}")

    print("Checking Firebase login...")
    if run_cmd("firebase projects:list", capture=True, quiet=True).returncode != 0:
        print("⚠️  You are not logged into Firebase. Launching login flow...")
        subprocess.run("firebase login", shell=True)
    else:
        print("✅ Authenticated with Firebase.")
    print("🎉 Cloud authentication verified!\n")

def run_cmd(cmd, cwd=None, capture=False, quiet=False):
    """Utility to run shell commands."""
    if not quiet:
        print(f"\n> Running: {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd, text=True, capture_output=capture)
    if result.returncode != 0 and not capture and not quiet:
        print(f"⚠️ Command returned non-zero exit code: {cmd}")
    return result

def ask(question, options=None, default=None):
    """Utility to prompt the user for input."""
    if options:
        prompt = f"{question} ({'/'.join(options)}): "
        while True:
            answer = input(prompt).strip().lower()
            if answer in options:
                return answer
    else:
        prompt_str = f"{question} [{default}]: " if default else f"{question}: "
        answer = input(prompt_str).strip()
        return answer if answer else default

def get_valid_app_name():
    """Ensures the app name matches Flutter's strict package naming requirements."""
    while True:
        name = ask("What is the name of your Flutter project? (e.g., danysz_flutter)")
        if not re.match(r'^[a-z][a-z0-9_]*$', name):
            valid_name = re.sub(r'[^a-z0-9_]', '', name.lower().replace("-", "_"))
            if not valid_name or not valid_name[0].isalpha():
                valid_name = "app_" + valid_name
            print(f"\n⚠️  Invalid Flutter project name. Must be lowercase, use underscores, and start with a letter.")
            if ask(f"Do you want to use '{valid_name}' instead?", ["y", "n"]) == 'y':
                return valid_name
        else:
            return name

# ==========================================
# CORE PIPELINE FUNCTIONS
# ==========================================

def gather_configuration():
    """Gathers all necessary inputs from the user to build the configuration state."""
    config = {}
    config['app_name'] = get_valid_app_name()
    config['org_domain'] = ask("What is your organization domain?", default="com.danyszflutter")
    config['fb_base_name'] = ask("What is the base name for your Firebase project?", default=f"{config['app_name'].replace('_', '-')}-app")
    config['env_choice'] = ask("How many Firebase environments?", ["1", "2"])
    config['setup_auth'] = ask("Do you need Google & Apple Sign-In?", ["y", "n"])
    
    config['environments'] = ["prod"] if config['env_choice'] == "1" else ["dev", "prod"]
    config['api_urls'] = {}
    for env in config['environments']:
        config['api_urls'][env] = ask(f"What is the API URL for the {env.upper()} environment?", default=f"https://api.{env}.yourdomain.com")

    config['git_repo_url'] = ask("Provide a link to an EMPTY Git repository (leave blank to skip pushing)", default="")

    # Core Directories
    config['root_dir'] = os.path.abspath(config['app_name'])
    config['mobile_dir'] = os.path.join(config['root_dir'], "mobile")
    config['keys_dir'] = os.path.join(config['root_dir'], "_keys")
    config['scripts_dir'] = os.path.join(config['root_dir'], "scripts")
    
    return config

def initialize_workspace(config):
    """Creates the folder structure, injects scripts, and runs flutter create."""
    print("\n--- 🔨 Creating Workspace & Injecting Scripts ---")
    os.makedirs(config['root_dir'], exist_ok=True)
    os.makedirs(config['keys_dir'], exist_ok=True)
    os.makedirs(config['scripts_dir'], exist_ok=True)
    
    inject_automation_scripts(config)

    print("\n--- 🔨 Creating Flutter App (in /mobile) ---")
    run_cmd(f"flutter create --org {config['org_domain']} --project-name {config['app_name']} mobile", cwd=config['root_dir'])
    
    # Dockerfile
    with open(os.path.join(config['mobile_dir'], "Dockerfile"), "w") as f:
        f.write("""# Stage 1: Build the Flutter Web App
FROM cirrusci/flutter:stable AS build
WORKDIR /app
COPY . .
RUN flutter clean && flutter pub get && flutter build web --release
# Stage 2: Serve with Nginx
FROM nginx:alpine
COPY --from=build /app/build/web /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
""")

def provision_cloud_resources(config):
    """Creates Google Cloud and Firebase projects."""
    print("\n--- ☁️ Setting up Firebase/GCP ---")
    config['project_ids'] = {}
    
    for env in config['environments']:
        project_id = config['fb_base_name'] if config['env_choice'] == "1" else f"{config['fb_base_name']}-{env}"
        config['project_ids'][env] = project_id
        
        display_name = config['app_name'].replace("_", " ").title()
        print(f"Creating Firebase project: {project_id}...")
        run_cmd(f"gcloud projects create {project_id} --name=\"{display_name} {env.capitalize()}\"")
        run_cmd(f"firebase projects:addfirebase {project_id}")

def generate_security_keys(config):
    """Generates the Android Keystore and properties file if Auth is enabled."""
    if config['setup_auth'] == "y":
        print("\n--- 🔐 Generating Keystores ---")
        keystore_path = os.path.join(config['keys_dir'], "upload-keystore.jks")
        key_password = ask("Enter a password for your Android Keystore (Save this safely!)")
        
        run_cmd(f"keytool -genkey -v -keystore {keystore_path} -keyalg RSA -keysize 2048 -validity 10000 -alias upload -storepass {key_password} -keypass {key_password} -dname \"CN=Unknown, OU=Unknown, O=Unknown, L=Unknown, ST=Unknown, C=US\"")

        with open(os.path.join(config['mobile_dir'], "android", "key.properties"), "w") as f:
            f.write(f"storePassword={key_password}\nkeyPassword={key_password}\nkeyAlias=upload\nstoreFile=../../_keys/upload-keystore.jks\n")

def configure_flutterfire_and_env(config):
    """Configures FlutterFire, handles retry logic, extracts App IDs, and writes .env."""
    print("\n--- 🔥 Configuring FlutterFire & Extracting App IDs ---")
    extracted_app_ids = {}
    
    for env in config['environments']:
        print(f"\nConfiguring {env.upper()} environment...")
        
        max_retries = 5
        retry_delay = 10
        success = False
        
        for attempt in range(1, max_retries + 1):
            print(f"Attempt {attempt}/{max_retries}: Running flutterfire configure...")
            result = run_cmd(f"flutterfire configure --project={config['project_ids'][env]} --yes", cwd=config['mobile_dir'], capture=True, quiet=True)
            
            if result.returncode == 0:
                print("✅ FlutterFire configuration successful!")
                success = True
                break
            else:
                if attempt < max_retries:
                    print(f"⏳ Firebase backend is still syncing. Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    print(f"❌ FlutterFire failed after {max_retries} attempts.")
                    print(f"Error details: {result.stderr}")
        
        if success:
            print(f"Fetching Firebase App IDs for {env.upper()}...")
            result = run_cmd(f"firebase apps:list --project {config['project_ids'][env]} --json", capture=True, quiet=True)
            try:
                apps_data = json.loads(result.stdout)
                app_list = apps_data.get("result", apps_data) if isinstance(apps_data, dict) else apps_data
                for app in app_list:
                    if app.get("platform") == "ANDROID":
                        extracted_app_ids[f"{env.upper()}_ANDROID_APP_ID"] = app.get("appId", "")
                    elif app.get("platform") == "IOS":
                        extracted_app_ids[f"{env.upper()}_IOS_APP_ID"] = app.get("appId", "")
                print(f"✅ App IDs extracted for {env.upper()}")
            except Exception as e:
                print(f"⚠️ Warning: Could not auto-extract App IDs for {env}. Error: {e}")

    # Generate .env
    print("\n--- 📄 Generating .env File ---")
    env_content = ""
    for env in config['environments']:
        env_content += f"{env.upper()}_API_URL=\"{config['api_urls'][env]}\"\n"
        env_content += f"{env.upper()}_ANDROID_APP_ID=\"{extracted_app_ids.get(f'{env.upper()}_ANDROID_APP_ID', 'TODO')}\"\n"
        env_content += f"{env.upper()}_IOS_APP_ID=\"{extracted_app_ids.get(f'{env.upper()}_IOS_APP_ID', 'TODO')}\"\n\n"
    
    with open(os.path.join(config['root_dir'], ".env"), "w") as f:
        f.write(env_content)
    print("✅ .env file successfully created at the root of the project.")

def configure_localization(config):
    """Sets up the initial localization files and updates pubspec.yaml."""
    print("\n--- 🌍 Setting up Localization ---")
    
    # 1. Create l10n.yaml
    with open(os.path.join(config['mobile_dir'], "l10n.yaml"), "w") as f:
        f.write("arb-dir: lib/l10n\ntemplate-arb-file: app_en.arb\noutput-localization-file: app_localizations.dart\n")
        
    # 2. Create the translation directory and base arb file
    os.makedirs(os.path.join(config['mobile_dir'], "lib", "l10n"), exist_ok=True)
    with open(os.path.join(config['mobile_dir'], "lib", "l10n", "app_en.arb"), "w") as f:
        f.write('{\n  "helloWorld": "Hello World!"\n}')

    # 3. Add dependencies via Flutter CLI
    print("Adding localization dependencies...")
    run_cmd("flutter pub add intl", cwd=config['mobile_dir'], quiet=True)
    run_cmd("flutter pub add flutter_localizations --sdk=flutter", cwd=config['mobile_dir'], quiet=True)

    # 4. Inject generate: true into pubspec.yaml
    pubspec_path = os.path.join(config['mobile_dir'], "pubspec.yaml")
    with open(pubspec_path, "r") as f:
        pubspec_content = f.read()
    
    # Safely insert generate: true under the flutter: block
    if "generate: true" not in pubspec_content:
        pubspec_content = pubspec_content.replace(
            "\nflutter:\n", 
            "\nflutter:\n  generate: true\n"
        )
        with open(pubspec_path, "w") as f:
            f.write(pubspec_content)

def initialize_git_repo(config):
    """Initializes Git, applies .gitignore, and handles remote pushing."""
    print("\n--- 🐙 Initializing Git & Pushing to Remote ---")
    run_cmd("git init", cwd=config['root_dir'])

    gitignore_content = """# Keys and Secrets
_keys/
.env

# OS generated files
.DS_Store
Thumbs.db
"""
    with open(os.path.join(config['root_dir'], ".gitignore"), "w") as f:
        f.write(gitignore_content)
    
    run_cmd("git add .", cwd=config['root_dir'])
    run_cmd('git commit -m "chore: initial commit from Danysz Flutter mono-repo generator"', cwd=config['root_dir'])
    run_cmd("git branch -M main", cwd=config['root_dir'])

    if config['git_repo_url']:
        print(f"Adding remote origin: {config['git_repo_url']}")
        run_cmd(f"git remote add origin {config['git_repo_url']}", cwd=config['root_dir'])
        print("Pushing to remote repository...")
        run_cmd("git push -u origin main", cwd=config['root_dir'])
        print("✅ Successfully pushed to remote.")
    else:
        print("✅ Repository initialized locally (no remote URL provided).")

# ==========================================
# POST-INSTALLATION CONSOLE OUTPUT
# ==========================================

def print_post_install_guide():
    """Prints documentation and portfolio links to the console after generation."""
    print("\n" + "="*60)
    print(" 🚀 DANYSZ FLUTTER AUTOMATION TOOLKIT - READY!")
    print("="*60)
    print("\nYour workspace is configured. Here are the tools injected into ./scripts:\n")
    
    print("📦 CI/CD & DEPLOYMENT")
    print("  • deploy_mobile.sh [d|p|dp] : Builds and deploys Dev/Prod flavors to Firebase.")
    print("  • deploy_web_test.sh        : Pushes an isolated Flutter Web build to your host.")
    print("  • bump_mobile_version.sh    : Automates patch/minor version bumps in pubspec.yaml.\n")
    
    print("🔐 SECURITY & AUTHENTICATION")
    print("  • generate_keystore.sh      : Safely creates your 2048-bit RSA production keystore.")
    print("  • setup_firebase_auth.sh    : Extracts SHA hashes required for Google Sign-In.\n")
    
    print("🌍 LOCALIZATION (L10N)")
    print("  • run_l10n_pipeline.sh      : The master orchestrator for translation automation.")
    print("  • extract_strings.py        : Hunts down hardcoded UI text and moves it to your .arb file.")
    print("  • fix_analyze.py            : Auto-resolves 'invalid const' errors caused by string extraction.")
    print("  • fix_context.py            : Injects BuildContexts into DataGridSources for translation access.")
    
    print("\n" + "="*60)
    print(" 👤 ABOUT THE CREATOR")
    print("="*60)
    print("  Built by Danysz.")
    # TODO: Replace these placeholders with your actual URLs!
    print("  • Documentation & Portfolio : https://[YOUR-USERNAME].github.io")
    print("  • Connect on LinkedIn       : https://linkedin.com/in/[YOUR-PROFILE]")
    print("="*60 + "\n")


# ==========================================
# SCRIPT INJECTION DICTIONARY
# ==========================================

def inject_automation_scripts(config):
    """Writes all provided user scripts to the scripts directory and makes them executable."""
    scripts = {}

    scripts["bump_mobile_version.sh"] = r"""#!/bin/bash
set -e
VERSION_TYPE=$1
if [[ "$VERSION_TYPE" != "patch" && "$VERSION_TYPE" != "minor" ]]; then
  echo "Usage: ./bump_mobile_version.sh [patch|minor]"
  exit 1
fi
echo "Bumping mobile version ($VERSION_TYPE)..."
PUBSPEC_PATH="mobile/pubspec.yaml"
CURRENT_VERSION_LINE=$(grep "^version:" $PUBSPEC_PATH)
CURRENT_VERSION_STRING=$(echo $CURRENT_VERSION_LINE | sed 's/version: //')
BASE_VERSION=$(echo $CURRENT_VERSION_STRING | cut -d+ -f1)
IFS='.' read -r MAJOR MINOR PATCH <<< "$BASE_VERSION"
MAJOR=$((10#$MAJOR))
MINOR=$((10#$MINOR))
PATCH=$((10#$PATCH))
if [ "$VERSION_TYPE" == "patch" ]; then PATCH=$((PATCH + 1))
elif [ "$VERSION_TYPE" == "minor" ]; then MINOR=$((MINOR + 1)); fi
FORMATTED_MINOR=$(printf "%02d" $MINOR)
FORMATTED_PATCH=$(printf "%02d" $PATCH)
FINAL_VERSION="$MAJOR.$FORMATTED_MINOR.$FORMATTED_PATCH+${MAJOR}${FORMATTED_MINOR}${FORMATTED_PATCH}"
sed -i '' "s/^version: .*/version: $FINAL_VERSION/" $PUBSPEC_PATH
git add $PUBSPEC_PATH
git commit -m "chore: bump mobile version to $FINAL_VERSION"
echo "Mobile version bumped to $FINAL_VERSION"
"""

    scripts["deploy_mobile.sh"] = r"""#!/bin/bash
set -e

if [ -f "./.env" ]; then export $(grep -v '^#' ./.env | xargs)
else echo "❌ Error: .env file not found in the root directory!"; exit 1; fi

if [ -z "$1" ]; then echo "Usage: ./scripts/deploy_mobile.sh [d|p|dp]"; exit 1; fi

DEPLOY_DEV=false
DEPLOY_PROD=false
if [[ "$1" == *"d"* ]]; then DEPLOY_DEV=true; fi
if [[ "$1" == *"p"* ]]; then DEPLOY_PROD=true; fi

FAILED=0

deploy_env() {
    local ENV_NAME=$1
    local API_URL=$2
    local ANDROID_APP_ID=$3
    local IOS_APP_ID=$4

    echo "================================================="
    echo "   Deploying $ENV_NAME environment apps          "
    echo "================================================="
    cd mobile
    flutter clean && flutter pub get

    echo "Building Android APK ($ENV_NAME flavor)..."
    if flutter build apk --flavor $ENV_NAME --dart-define=APP_ENV="$ENV_NAME" --dart-define=API_URL="$API_URL"; then
        if ! firebase appdistribution:distribute build/app/outputs/flutter-apk/app-$ENV_NAME-release.apk --app "$ANDROID_APP_ID" --groups "internal" --release-notes "$ENV_NAME release"; then FAILED=1; fi
    else FAILED=1; fi

    echo "Building iOS IPA ($ENV_NAME flavor)..."
    if flutter build ipa --flavor $ENV_NAME --export-method development --dart-define=APP_ENV="$ENV_NAME" --dart-define=API_URL="$API_URL"; then
        IPA_FILE=$(find build/ios/ipa -name "*.ipa" | head -n 1)
        if [ -n "$IPA_FILE" ]; then
            if ! firebase appdistribution:distribute "$IPA_FILE" --app "$IOS_APP_ID" --groups "internal" --release-notes "$ENV_NAME release"; then FAILED=1; fi
        else FAILED=1; fi
    else FAILED=1; fi
    cd ..
}

if [ "$DEPLOY_DEV" = true ]; then deploy_env "dev" "$DEV_API_URL" "$DEV_ANDROID_APP_ID" "$DEV_IOS_APP_ID"; fi
if [ "$DEPLOY_PROD" = true ]; then deploy_env "prod" "$PROD_API_URL" "$PROD_ANDROID_APP_ID" "$PROD_IOS_APP_ID"; fi

if [ "$FAILED" -eq 1 ]; then echo "❌ Deployments failed. Exiting without bumping versions."; exit 1; fi

if [[ "$*" != *"--skip-version-bump"* ]]; then
    if [ "$DEPLOY_PROD" = true ]; then ./scripts/bump_mobile_version.sh minor
    elif [ "$DEPLOY_DEV" = true ]; then ./scripts/bump_mobile_version.sh patch; fi
fi
exit 0
"""

    scripts["deploy_web_test.sh"] = r"""#!/bin/bash
set -e
git branch -D deploy-web-test 2>/dev/null || true
git subtree split --prefix mobile -b deploy-web-test
git push web-test deploy-web-test:main --force
git branch -D deploy-web-test
if [[ "$*" != *"--skip-version-bump"* ]]; then ./scripts/bump_mobile_version.sh patch; fi
"""

    scripts["generate_keystore.sh"] = r"""#!/bin/bash
set -e
KEYSTORE_FILE="./_keys/upload-keystore.jks"
if [ -f "$KEYSTORE_FILE" ]; then
    read -p "Keystore exists. Overwrite? (y/N) " -n 1 -r; echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then exit 1; fi
    rm "$KEYSTORE_FILE"
fi
keytool -genkey -v -keystore "$KEYSTORE_FILE" -keyalg RSA -keysize 2048 -validity 10000 -alias upload
"""

    scripts["setup_firebase_auth.sh"] = r"""#!/bin/bash
set -e
if ! command -v firebase &> /dev/null; then exit 1; fi
firebase login --interactive
extract_sha() {
    if [ -f "$1" ]; then keytool -list -v -keystore "$1" -alias "$2" -storepass "$3" -keypass "$3" 2>/dev/null | grep -A 2 "Certificate fingerprints:" | grep "$4:" | awk '{print $2}'; fi
}
echo "--- Extracting Hashes ---"
extract_sha "$HOME/.android/debug.keystore" "androiddebugkey" "android" "SHA1"
extract_sha "$HOME/.android/debug.keystore" "androiddebugkey" "android" "SHA256"
"""

    scripts["extract_strings.py"] = r"""import os, re, json
src_dir, l10n_dir = 'mobile/lib/src', 'mobile/lib/l10n'
def to_camel_case(text):
    words = re.sub(r'[^a-zA-Z0-9 ]', '', text).split()
    return words[0].lower() + ''.join(w.capitalize() for w in words[1:]) if words else "emptyStr"
arb_files = [f for f in os.listdir(l10n_dir) if f.endswith('.arb')]
arbs = {arb: json.load(open(os.path.join(l10n_dir, arb), 'r')) for arb in arb_files}
pattern = re.compile(r'(?P<before>Text\(\s*|(?:title|label|hintText|tooltip|labelText|content|message):\s*)(?P<string>[\'"])(?P<text>[^\'"\$]+?)(?P=string)')

def process_file(filepath):
    with open(filepath, 'r') as f: content = f.read()
    content = re.sub(r'const\s+(Text\([^\)]+\)|(?:title|label|hintText|tooltip|labelText|content|message):\s*[\'"][^\'"]+[\'"])', r'\1', content)
    changed = False
    def repl(m):
        nonlocal changed
        before, text = m.group('before'), m.group('text').strip()
        if len(text) < 2 or text.isnumeric(): return m.group(0)
        changed, key = True, to_camel_case(text)
        base_arb = 'app_en.arb' if 'app_en.arb' in arbs else arb_files[0]
        while key in arbs[base_arb] and arbs[base_arb][key] != text: key += "1"
        for arb_dict in arbs.values():
            if key not in arb_dict: arb_dict[key] = text
        return f"{before}AppLocalizations.of(context)!.{key}"
    new_content = pattern.sub(repl, content)
    if changed:
        if "AppLocalizations" not in content:
            rel_path = os.path.relpath(os.path.abspath(os.path.join(l10n_dir, 'app_localizations.dart')), os.path.dirname(os.path.abspath(filepath)))
            new_content = f"import '{rel_path}';\n" + new_content
        with open(filepath, 'w') as f: f.write(new_content)

for root, _, files in os.walk(src_dir):
    for f in files:
        if f.endswith('.dart'): process_file(os.path.join(root, f))
for arb_name, arb_dict in arbs.items():
    with open(os.path.join(l10n_dir, arb_name), 'w') as f: json.dump(arb_dict, f, indent=2, ensure_ascii=False)
"""

    scripts["fix_analyze.py"] = r"""import re
try:
    with open('/tmp/analyze.log', 'r') as f: lines = f.readlines()
    for line in lines:
        if 'invalid_constant' in line:
            parts = [p.strip() for p in line.split('•')]
            if len(parts) >= 4:
                filepath, line_idx = 'mobile/' + parts[2].split(':')[0], int(parts[2].split(':')[1]) - 1
                with open(filepath, 'r') as file: file_lines = file.readlines()
                for offset in range(0, min(5, line_idx + 1)):
                    idx = line_idx - offset
                    if 'const ' in file_lines[idx]:
                        file_lines[idx] = re.sub(r'\bconst\s+(SnackBar|SizedBox|Text|Row|Column|Padding|Center|Tooltip|Expanded|Align|Container|Icon|InputDecoration|AlertDialog|TextSpan)\b', r'\1', file_lines[idx])
                        break
                with open(filepath, 'w') as file: file.writelines(file_lines)
except Exception as e: print(f"Error fixing analyze: {e}")
"""

    scripts["fix_context.py"] = r"""import os, re
for root, _, files in os.walk('mobile/lib/src/screens'):
    for f in files:
        if f.endswith('.dart'):
            filepath = os.path.join(root, f)
            with open(filepath, 'r') as file: content = file.read()
            if 'extends DataGridSource' in content and 'final BuildContext context;' not in content:
                content = re.sub(r'(class _[A-Za-z]+DataSource(?:<.+>)? extends DataGridSource \{)', r'\1\n  final BuildContext context;', content)
                content = re.sub(r'(_[A-Za-z]+DataSource\(\{)', r'\1\n    required this.context,', content)
                content = re.sub(r'(_[A-Za-z]+DataSource\((?!\{))', r'\1\n            context: context,', content)
                with open(filepath, 'w') as file: file.write(content)
"""

    scripts["run_l10n_pipeline.sh"] = r"""#!/bin/bash
python3 scripts/extract_strings.py
(cd mobile && flutter analyze > /tmp/analyze.log || true)
python3 scripts/fix_analyze.py
python3 scripts/fix_context.py
"""

    for filename, content in scripts.items():
        filepath = os.path.join(config['scripts_dir'], filename)
        with open(filepath, "w") as f:
            f.write(content)
        if filename.endswith(".sh"): os.chmod(filepath, 0o755)


# ==========================================
# MAIN ORCHESTRATOR
# ==========================================

def main():
    print("🚀 Welcome to the Danysz Flutter Zero-Touch Mono-Repo Generator!")
    
    check_dependencies()
    check_auth()
    
    config = gather_configuration()
    
    initialize_workspace(config)
    provision_cloud_resources(config)
    generate_security_keys(config)
    configure_flutterfire_and_env(config)
    configure_localization(config)
    initialize_git_repo(config)

    # Trigger the newly added post-installation guide!
    print_post_install_guide()

if __name__ == "__main__":
    main()
