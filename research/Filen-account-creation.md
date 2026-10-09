# Filen: tested signup and API access

Tested 9 October 2026. **Account creation and API authentication passed, but the account received zero storage.** It cannot contribute capacity to the proposed free archive. No CAPTCHA, phone number, or payment was requested.

## Route taken

1. Create a test inbox through the [Mail.tm API](https://docs.mail.tm/) ([Mail.tm](https://mail.tm/)). Use a durable inbox for real storage.
2. Open https://app.filen.io/#/register in an isolated Chrome profile.
3. Choose **Only needed** for cookies.
4. Record the eligibility indicator. This session displayed **“You are not eligible for 10 GiB of free storage.”** The user explicitly requested completing the test despite this previously observed limitation.
5. Fill email, password, and password confirmation. Sequential typing and an exact input-value check were used before submission.
6. Click **Create account**. Filen reported account creation and sent a confirmation email.
7. Follow the HTTPS Filen activation link from the message. The site reported **Account activated**.
8. Open https://app.filen.io/#/login and sign in. Cloud Drive opened with **0 Bytes of 0 Bytes used** and a master-key export prompt.

No referral was used, and no attempt was made to bypass the network eligibility check. Master keys were not exported through the browser during this test.

## API test and measured result

The provider's [official CLI repository](https://github.com/FilenCloudDienste/filen-cli) currently recommends release **v0.0.36** while the CLI is being replaced. The Windows executable was downloaded from that official GitHub release and its full size and SHA-256 digest were verified against the GitHub release metadata before execution. The executable's help banner prints `0.0.0`; the downloaded release asset is v0.0.36.

The CLI was invoked with updates disabled and a separate task-specific data directory. Credentials were supplied in the documented `FILEN_EMAIL` and `FILEN_PASSWORD` environment variables. `export-api-key` authenticated successfully. Its output was captured privately and the API key was immediately saved in the existing Windows DPAPI-encrypted vault.

The [rclone Filen backend](https://rclone.org/filen/) was configured through subprocess environment variables using backend type `filen`, email, password, and the exported API key. Password/key values were supplied in rclone's obscured format; obfuscation itself is not secure storage. `--config NUL` avoided changing any user rclone configuration.

| Check | Result |
|---|---|
| Official CLI authentication / API-key export | Passed |
| Authenticated quota query | Passed: total 0, used 0, free 0 bytes |
| Authenticated object listing | Passed: zero objects |
| Upload generated 54-byte text file | Rejected: `Maximum storage reached. max_storage_reached` |
| Download / byte-hash verification | Not possible because upload was rejected |

No personal files were uploaded. The rejected upload created no successful test object. No remote deletion was needed.

## Effect on the archive plan

Filen's signup is functional without a CAPTCHA in this test, and its account API can be integrated. **The nominal free 10 GiB is conditional on eligibility and was not granted here.** The proposed two-Filen-per-MEGA ratio applies only to accounts whose measured quota is actually 10 GiB; it cannot use these zero-capacity accounts.

[Filen's eligibility documentation](https://filen.io/hub/free-10-gb-at-signup-eligibility-check-before-creating-an-account/) says the free grant happens at signup and is not rechecked later. This existing zero-capacity test account should therefore not be assumed to become a 10 GiB account later. A legitimately eligible contributor account is needed to finish the authenticated upload/download test.

## Saved scripts and evidence

- `filen_signup_test.py`: signup, activation, and login.
- `prepare_filen_cli.py`: official release discovery/download and hash verification.
- `filen_api_test.py`: CLI authentication, key export, quota/listing, and a bounded generated-file upload test.
- `signup-evidence/filen-before-signup.json`: eligibility warning.
- `signup-evidence/filen-after-submission.json`: account creation accepted.
- `signup-evidence/filen-after-activation.json`: activation accepted.
- `signup-evidence/filen-after-login.json`: signed-in Cloud Drive and zero quota.
- `signup-evidence/filen-api-test.json`: machine-readable API results.

The generated cloud/mailbox credentials and account API key are retained in `test-credentials.dpapi`, encrypted for this Windows user. The isolated browser profile is under the task-specific temporary profile directory. Never distribute the API key to frontend users.
