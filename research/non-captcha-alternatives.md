# Alternatives to CAPTCHA-blocked free cloud signup

Checked 9 October 2026. Goal: a second provider for the shared, mirrored archive, around 20 GB free per contributed account, with programmatic file access. No additional CAPTCHA was solved in this investigation. The cause of Google's previous generic account-creation error remains unknown; bot detection is a hypothesis, not a confirmed ban.

**Later live Filen test:** A new account was created, email-activated, and signed in without a CAPTCHA. Official CLI authentication and rclone quota/listing passed, but measured capacity was **0 bytes**. A generated 54-byte upload was rejected with `max_storage_reached`. The full procedure and evidence are saved in [Filen-account-creation.md](Filen-account-creation.md). The earlier observations below describe the initial screening; Filen is now tested for account/API access, but has no usable free capacity on this test connection.

## Closest candidate: Filen

- Signup route: https://app.filen.io/#/register. The inspected page had email, password, password confirmation, and no CAPTCHA frame or visible CAPTCHA.
- The normal free allocation is marketed as 10 GB; the live page referred to 10 GiB. A valid referral signup can add another 10 GB, reaching 20 GB. Referral storage is conditional, not automatic.
- The live page displayed **“You are not eligible for 10 GiB of free storage.”** on this test connection. No account was created because the intended free capacity would not be granted. This was not a CAPTCHA failure.
- [Filen's eligibility explanation](https://filen.io/hub/free-10-gb-at-signup-eligibility-check-before-creating-an-account/) describes a one-time network classification. VPN, proxy, hosting, and some shared networks can fail the check. [The referral explanation](https://filen.io/hub/status-update-february-march-2026/) also requires both parties' signup connections to be residential, different IPs, and additional referral conditions.
- [Official CLI](https://docs.filen.io/docs/cli/) and [native rclone backend](https://rclone.org/filen/) exist. The documented rclone setup requires email, password, and an account API key exported through the Filen CLI. Authenticated file operations were not tested because there was no eligible free account.
- [Filen's roadmap](https://filen.io/hub/roadmap/) dates formation of the company to May 2021. Its relatively short operating history means long-term survival cannot be treated as established. This is a reason to retain MEGA as an independent copy and preserve migration capability.

Filen is the best next candidate for eligible individual contributors; it is not a verified provider for fully unattended signup from this particular test connection. No CAPTCHA observed in a form does not guarantee that no security challenge will ever appear.

## Other live checks

| Provider | Capacity from current primary sources | What the test established |
|---|---|---|
| Degoo | [20 GB free](https://degoo.com/features) | A new email/password account was created without a CAPTCHA appearing, and its saved session opened `/moments`. The desktop web app then displayed **“Premium required to use Degoo on desktop.”** The account's quota and file API were not verified. No paywall workaround was attempted. |
| Koofr | [10 GB free](https://koofr.eu/) | Initial signup had no CAPTCHA. Submitting the email triggered **“Type the digits from the image below”** and a `captchaDigits` field. No account was created. Its [WebDAV support](https://koofr.eu/help/koofr_with_webdav/how-do-i-connect-a-service-to-koofr-through-webdav/) is documented, but the signup fails the requested condition in this test. |
| pCloud | [2 GB initially; up to 10 GB with tasks/referrals](https://help.pcloud.com/article/plan-details) | Its live signup included an invisible reCAPTCHA frame. No signup was submitted; capacity also falls short of 20 GB. |
| Drime | [20 GB free](https://drime.cloud/cloud-storage) | Signup included an invisible reCAPTCHA frame. No account was created. It has a documented [REST API and rclone support](https://drime.cloud/developer), but it fails a strict no-CAPTCHA requirement. [Its own company page](https://drime.cloud/about-us) dates founding to 2024, adding a short-history risk for a decades-long archive. |

Degoo's advertised free plan also lists 90 days of account inactivity. Even apart from the desktop restriction, a background archive would need a verified maintenance route; merely storing bytes is not proof the account will remain active. I did not find an official public file API contract to validate for this account.

## Evidence and preserved credentials

- Filen form screenshot: `signup-evidence/filen-signup.png`.
- Koofr result: `signup-evidence/koofr-after-email-submission.json`.
- Degoo submission and signed-in session: `signup-evidence/degoo-after-submission.json` and `signup-evidence/degoo-session-check.json`.
- Drime form/frame evidence: `signup-evidence/drime-signup-observations.json`.
- Test scripts: `alternative_signup_probe.py`, `koofr_signup_test.py`, and `degoo_signup_test.py`.
- Degoo's generated account credentials and Koofr's uncompleted signup mailbox are retained in the existing Windows DPAPI-encrypted `test-credentials.dpapi`; no personal files were uploaded.

MEGA remains the only provider so far with a newly created account and a complete authenticated quota/upload/list/download/hash check. Filen is the closest researched second-provider candidate, contingent on eligible signup and successful referral credit.
