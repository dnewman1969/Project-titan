# Third-party licences

Third-party binaries are never committed. `tools/fetch-third-party.py` downloads them into
`third_party/cache/` (git-ignored) and verifies each one against the SHA-256 and size pinned in
[`../manifest.yaml`](../manifest.yaml).

| Artifact                           | Version | Licence                               | Shipped in installer                           |
| ---------------------------------- | ------- | ------------------------------------- | ---------------------------------------------- |
| PostgreSQL (EDB portable binaries) | 16.15-1 | PostgreSQL                            | Yes                                            |
| FFmpeg (gyan.dev essentials)       | 7.1.1   | GPL-3.0-or-later                      | Yes, with licence text and source offer        |
| PresentMon                         | 2.6.0   | MIT                                   | Yes                                            |
| kRPC                               | 0.5.4   | LGPL-3.0, and GPL-3.0 for SpaceCenter | No. Installed into KSP after user consent      |
| scs-sdk-plugin                     | 1.12.1  | MIT                                   | No. Installed into ETS2/ATS after user consent |

When the installer is built (M10), each shipped artifact's licence text goes into this folder as
`<artifact-id>.txt`, and `release.yml` attaches a generated licence report and CycloneDX SBOM.
Memurai's licence must be reviewed before distribution (risk R9).
