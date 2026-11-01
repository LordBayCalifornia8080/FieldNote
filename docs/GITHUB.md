# Publish this source on GitHub

Extract the ZIP first. The archive is source code, not a running website. Do not upload the ZIP as your only repository file if you want GitHub to show the source and README normally.

1. Create a new repository using GitHub's web interface. Choose public if desired. Leave automatic README/license creation off because this source includes both.
2. Use **uploading an existing file** on an empty repository, or **Add file → Upload files** in an existing one.
3. Drag the contents of the extracted `fieldnotes` folder into the upload area. `README.md`, `pyproject.toml`, `compose.yaml`, and the `fieldnotes/` package should be at the repository root, not under an extra wrapper directory.
4. Include hidden repository configuration such as `.github`, `.gitignore`, `.dockerignore`, `.gitattributes`, and `.env.example`. Enable hidden-file display in your file manager if necessary. GitHub Desktop is an alternative when browser folder selection omits hidden files.
5. Review the staged file list and commit. Verify that the README renders and `.github/workflows/ci.yml` exists.

The package excludes databases, real `.env` files, credentials, dependency installations, and personal author information. Do not add those files later. Example usernames/password strings in tests are synthetic local test fixtures. The publisher identity on GitHub and the author email in commits are controlled by your GitHub account/settings, not by this source package. Set your preferred privacy settings before committing.

Publishing the code does not host the application, create user accounts, or incur server costs by itself. GitHub Pages cannot run this Python backend. Users clone/download the repository and run it on their own server. The included CI workflow executes tests/build checks under GitHub Actions; review your account's current Actions usage settings and policies.

If you leave the repository without maintaining it, retain the explicit maintenance policy in README and SECURITY. GitHub's archive feature can mark a repository read-only. Neither a maintenance note nor a software license guarantees protection from all legal obligations; this repository does not offer a legal assessment.
