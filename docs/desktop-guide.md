# GenomeDebugger local desktop build

Extract the entire archive to a new folder and open **GenomeDebugger.exe**. The package contains its Python runtime and the built interface; Node.js and a separate Python installation are not required for running this package.

Verification status: package generation and the source launcher smoke test passed. Automatic approval review blocked launching the generated executable with the reason “blocked by policy,” so execution of the frozen binary remains unverified. This local build has not been publicly released or code-signed.

The workspace opens at http://127.0.0.1:8765/. It accepts loopback connections only. Data is stored in `%LOCALAPPDATA%\GenomeDebugger\data`, separately from the extracted application. The development checkout uses its own `data` folder; transfer selected comparisons with full bundles or deliberately restore a database backup rather than assuming the two installations share records.

Use **Local data → Stop application** to stop the portable server. Closing a browser tab alone does not stop it. Reopening the executable reuses a running desktop workspace only when its data location matches.

## Backups and updates

Download a database backup from Local data before replacing a release. Stop the application, extract a new release into a new folder, and launch that version. The launcher also preserves an existing database once per release in `data\backups\before-VERSION.db`. Keep your previous executable folder until the new version has been checked. The archive SHA-256 detects a mismatched download; it is not a signing identity. Automatic updates are not enabled.

This is a local build, not a signed published installer. Code signing and public distribution require a separate release process. Optional local SnpEff execution still requires its declared Java/tool/database artifacts; the basic comparison and public-source workflows do not require SnpEff.

To restore a downloaded database backup, stop the application first, keep a separate copy of your current database, and run `GenomeDebugger.exe --restore-backup "C:\path\to\genomedebugger-backup.db"` from the extracted folder. The validated restore operation preserves the previous database before replacing it. Reopen GenomeDebugger afterward. Browser-local saved drafts are separate from database backups.

## Developer build

Run `scripts\build-desktop.ps1` from the checkout. It creates a unique folder under `release`, builds the interface, packages Python dependencies with pinned PyInstaller, copies the reference fixtures, and creates a ZIP plus SHA-256 file. It does not copy the development database or personal files.

The source checkout also provides Setup/Start/Stop GenomeDebugger launchers. Setup requires Python and Node.js, installs the pinned project dependencies, and creates a desktop shortcut; the portable build avoids those runtime prerequisites.
