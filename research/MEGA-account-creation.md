# MEGA: tested account creation and API access

Test date: 9 October 2026. A usable free account was independently created and activated in an isolated Chrome profile. Only generated test data was uploaded.

## Signup route that succeeded

1. Obtain an email inbox that can receive the activation message. This test used a receive-only mailbox created with the [Mail.tm API](https://docs.mail.tm/) ([Mail.tm](https://mail.tm/)). Its [FAQ](https://mail.tm/en/faq/) says the address remains valid until the mailbox is deleted and domains are renewed. Messages last seven days, outgoing email is unavailable, and forgotten passwords cannot be reset.
2. Open [MEGA registration](https://mega.nz/register).
3. Enter a name, email address, and a strong unique password; submit **Sign up**.
4. Receive MEGA's activation email and open its confirmation link. In this test the link was opened in the same browser session as registration.
5. At **Confirm your account**, enter the same password and select **Confirm**.
6. The browser reached MEGA's recovery-key screen. Save the recovery key separately before using the account for valuable files; completion of that key-export step was not part of this test.

No phone number, card, payment, or CAPTCHA was requested on this successful route. A single successful test does not guarantee identical signup requirements for every future account.

## Browser automation lesson

The first automated password entry silently lost two characters. That initial attempt was not usable. A replacement registration succeeded after using sequential typing and checking that the field value exactly matched the intended password before submitting. Do not repeatedly create accounts to hide an input bug; verify the entered value first.

The working helper is `type_secret` in `cloud_signup_execute.py`: clear the field, focus it, type sequentially, and confirm exact equality before advancing. The successful action was `mega complete`, which registers and activates in one browser session.

## Working API procedure

The live API test used [rclone's MEGA backend](https://rclone.org/mega/) with rclone 1.75.2. Its portable Windows archive was downloaded from the official rclone site and checked against the published SHA-256 checksum.

- Backend type: `mega`.
- Authenticate with the account email and password. Supply the password in the format produced by `rclone obscure`; that format is obfuscation, not secure credential storage.
- Test configuration was supplied in subprocess environment variables with `--config NUL`, so the user's existing rclone configuration was untouched.
- `rclone about test_mega: --json` returned total/free **21,474,836,480 bytes (20 GiB)** and zero usage.
- Upload a uniquely named generated text file, list it, download it, and compare SHA-256 hashes.
- Delete only that generated remote test object.

All five checks passed. The uploaded payload was 54 bytes; large-file handling, throughput, transfer quotas, and sustained production use remain untested.

The reusable test is `mega_api_test.py`; machine-readable evidence is `signup-evidence/mega-api-test.json`.

## Credentials and integration options

Generated credentials are saved in `test-credentials.dpapi`, encrypted using Windows DPAPI for this Windows user. They are not embedded in this document or the scripts. The isolated browser profile remains under the task-specific temporary profile directory. This is a research account. Mail.tm does not impose a mailbox expiry in its current FAQ, but a receive-only inbox with no password reset still needs its credentials preserved separately.

For the shared frontend, a server-side worker can use the tested backend. MEGA also provides an [official SDK](https://mega.io/sdk) and [official MEGAcmd](https://github.com/meganz/MEGAcmd), including documented [signup](https://github.com/meganz/MEGAcmd/blob/master/contrib/docs/commands/signup.md) and [confirmation](https://github.com/meganz/MEGAcmd/blob/master/contrib/docs/commands/confirm.md) commands. Those command-line signup routes were reviewed in documentation, but this test created the account through the website.

Keep credentials in the backend rather than distributing them to every frontend user. A mirrored upload should be marked protected only after both providers return successful writes and the stored bytes have been verified. Export the catalogue and preserve recovery keys so the archive can be moved when a provider or free plan changes.
