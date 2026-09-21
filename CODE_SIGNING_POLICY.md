# Code signing policy

**Free code signing provided by [SignPath.io](https://about.signpath.io/), certificate by [SignPath Foundation](https://signpath.org/).**

> *Status:* the application to the SignPath Foundation is in progress. Until it is approved, the published binaries are
> **not signed** (Windows SmartScreen may warn). This page describes the policy that will apply once they are.

## What is signed
Only binaries built **from this repository** by the public [GitHub Actions workflow](.github/workflows/build.yml):
`NavTool.exe`, the installer (`NavTool-Setup-<version>.exe`) and the uninstaller. Third-party files bundled in the portable
package (the Python runtime and Tk libraries) keep their own signatures and are not re-signed. Builds are never made or signed
on a personal computer.

## Team and roles
| Role | Person |
|---|---|
| Author / committer | Fernando Erazo ([@xev777](https://github.com/xev777)) |
| Reviewer (approves pull requests from non-committers) | Fernando Erazo ([@xev777](https://github.com/xev777)) |
| Approver (authorizes each signing request) | Fernando Erazo ([@xev777](https://github.com/xev777)) |

All maintainers use multi-factor authentication on GitHub and on SignPath. Changes from anyone else arrive as pull requests that
a reviewer must approve before merging.

## What NavTool does to your system (announced)
NavTool is a network monitor and filter. It does **only** what you ask for, and every change is reversible from the app:
* turns the Windows **proxy** (`127.0.0.1`) on/off (⏻ button) and restores it on exit;
* creates Windows Firewall rules named `NavTool block: …` to block a program you choose (needs administrator);
* adds Windows loopback exemptions for Microsoft Store apps you choose (needs administrator);
* optionally starts with Windows (`HKCU\…\Run`).
The uninstaller removes all of the above.

## Privacy
See [PRIVACY.md](PRIVACY.md): **this program will not transfer any information to other networked systems unless specifically
requested by the user or the person installing or operating it.**
