# Security Policy

Argus takes the "Security First" constitution principle literally. This file says how to report problems and what to expect.

## Reporting a vulnerability

**Do not open a public issue for security bugs.** Create a private advisory via GitHub's security tab, or email the maintainers directly if you know who we are.

What helps the most in a report:

- Which module and version — `argus version` output is perfect
- A minimal reproduction: the smallest code snippet that triggers it
- Impact: what an attacker could actually do with it
- Whether you've already tested a fix

You'll get an acknowledgment within a few days. We don't have a bounty program, but you'll be credited in the changelog unless you ask not to be.

## What we consider in scope

- Secret vault bypass (Fernet/PBKDF2 weaknesses, key handling)
- Permission engine bypass — getting `security/` to allow something it shouldn't
- Sandbox escape from capability execution
- Injection through gateway auth or adapter inputs
- Unsafe deserialization anywhere in the framework

Out of scope: your own deployment config, credentials you committed to a repo, and issues in third-party dependencies (report those upstream).

## Security model, in one paragraph

The core assumption is that **capabilities are untrusted until checked**. Every execution passes through the security engine, which defaults to deny. The vault stores secrets encrypted at rest with a key derived via PBKDF2 — salt and iteration count live in the file header, so a stolen vault file without the passphrase is a blob of ciphertext. Sandboxing is best-effort isolation (THREAD mode shares a process; SUBPROCESS mode isolates further), so treat the sandbox as a mitigation layer, not a trust boundary.

## Supported versions

| Version | Supported |
|---|---|
| 1.1.x | ✅ |
| 1.0.x | ⚠️ critical fixes only |
| < 1.0 | ❌ |

## Disclosure

We prefer coordinated disclosure: give us time to ship a fix before the issue goes public. If you've already gone public, say so in the report — we'd rather know than find out.
